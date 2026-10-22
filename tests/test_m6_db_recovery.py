import hashlib,json,os,sqlite3,subprocess,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from ai_manager.db_recovery import copy_database_to_new_target
from ai_manager.inventory import Inventory
from ai_manager.dashboard import Dashboard

class M6DatabaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'fresh-source';self.inventory=Inventory(self.source)

    def test_fresh_database_backup_restore_new_target_and_actual_query(self):
        with self.inventory.connect() as db:
            db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid) VALUES(?,?,?,?,?,?,?)",('a'*32,'A',1,'{}','2026-10-17','complete',os.getpid()))
        backup=self.root/'backup.sqlite3';result=copy_database_to_new_target(self.inventory.db,backup)
        restored=self.root/'fresh-restored/inventory.sqlite3';copy_database_to_new_target(backup,restored)
        self.assertEqual(result['integrity'],'ok');self.assertEqual(Inventory(restored.parent).summary()['scans'][0]['scan_id'],'a'*32)
        self.assertEqual(Dashboard(restored.parent).query({})['scans'][0]['scan_id'],'a'*32)
        before=hashlib.sha256(restored.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'database_destination_exists'):copy_database_to_new_target(backup,restored)
        self.assertEqual(hashlib.sha256(restored.read_bytes()).hexdigest(),before)

    def test_corrupt_source_and_wrong_schema_preserved(self):
        corrupt=self.root/'damaged.sqlite3';corrupt.write_bytes(b'fresh deliberate database corruption')
        with self.assertRaisesRegex(ValueError,'database_unreadable_or_corrupt'):copy_database_to_new_target(corrupt,self.root/'new.sqlite3')
        self.assertEqual(corrupt.read_bytes(),b'fresh deliberate database corruption');self.assertFalse((self.root/'new.sqlite3').exists())
        wrong=self.root/'wrong.sqlite3'
        with closing(sqlite3.connect(wrong)) as db, db:db.execute('CREATE TABLE arbitrary(value TEXT)')
        with self.assertRaisesRegex(ValueError,'database_schema_unsupported'):copy_database_to_new_target(wrong,self.root/'new2.sqlite3')

    def test_same_column_names_without_constraints_rejected(self):
        clone=self.root/'clone.sqlite3'
        with closing(sqlite3.connect(clone)) as output, output, closing(sqlite3.connect(self.inventory.db)) as original, original:
            for table in ('scans','files'):
                names=[row[1] for row in original.execute('PRAGMA table_info('+table+')')]
                output.execute('CREATE TABLE '+table+'('+','.join(names)+')')
        with self.assertRaisesRegex(ValueError,'database_schema_unsupported'):copy_database_to_new_target(clone,self.root/'clone-restored.sqlite3')
        self.assertFalse((self.root/'clone-restored.sqlite3').exists())

    def test_lock_after_integrity_check_hits_backup_deadline(self):
        from ai_manager import db_recovery
        original_check=db_recovery._check;holder=sqlite3.connect(self.inventory.db,timeout=1)
        checked=False
        def check(connection):
            nonlocal checked
            original_check(connection)
            if not checked:
                holder.execute('BEGIN EXCLUSIVE');checked=True
        try:
            with patch('ai_manager.db_recovery._check',side_effect=check),patch('ai_manager.db_recovery.time.monotonic',side_effect=[0,11]):
                with self.assertRaisesRegex(ValueError,'database_backup_timeout'):copy_database_to_new_target(self.inventory.db,self.root/'timed-out.sqlite3')
            self.assertFalse((self.root/'timed-out.sqlite3').exists())
            self.assertTrue(list(self.root.glob('*.sqlite3.tmp')))
        finally:holder.rollback();holder.close()

    @unittest.skipUnless(os.name=='nt','Windows junction boundary')
    def test_destination_parent_junction_rejected(self):
        outside=self.root/'outside';outside.mkdir();link=self.root/'link'
        result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True);self.assertEqual(result.returncode,0)
        with self.assertRaisesRegex(ValueError,'unsafe_local_path'):copy_database_to_new_target(self.inventory.db,link/'restored.sqlite3')
        self.assertFalse((outside/'restored.sqlite3').exists())
