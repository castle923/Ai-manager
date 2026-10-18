import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ai_manager.security import protect_directory, _system_tool, private_acl_contract


@unittest.skipUnless(os.name == 'nt', 'Windows ACL subprocess contract')
class PrivateDirectoryStartup(unittest.TestCase):
    def test_system_tools_are_hidden_bounded_and_keep_acl_policy(self):
        calls=[]
        def run(argv, **options):
            calls.append((argv,options))
            return subprocess.CompletedProcess(argv,0,stdout='"user","S-1-5-21-123"\n',stderr='')
        with tempfile.TemporaryDirectory() as temporary, patch('ai_manager.external_process.run_external',side_effect=run), patch('ai_manager.security.directory_is_private',side_effect=[False,True]):
            protect_directory(Path(temporary)/'private')
        self.assertEqual(len(calls),2)
        for (argv,options),name,limit in zip(calls,('whoami.exe','icacls.exe'),(10,30)):
            self.assertEqual(argv[0],_system_tool(name))
            self.assertTrue(Path(argv[0]).is_absolute())
            self.assertEqual(options['timeout'],limit)
            self.assertEqual(options['creationflags'],subprocess.CREATE_NO_WINDOW)
            self.assertEqual(options['stdin'],subprocess.DEVNULL)
            self.assertTrue(options['capture_output'])
        self.assertTrue(calls[0][1]['check'])
        self.assertEqual(calls[1][0][2:],['/inheritance:r','/grant:r','*S-1-5-21-123:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'])

    def test_sid_timeout_fails_before_acl(self):
        with tempfile.TemporaryDirectory() as temporary, patch('ai_manager.external_process.run_external',side_effect=subprocess.TimeoutExpired('whoami',10)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):protect_directory(temporary)
            self.assertEqual(run.call_count,1)

    def test_invalid_sid_fails_before_acl(self):
        with tempfile.TemporaryDirectory() as temporary, patch('ai_manager.external_process.run_external',return_value=subprocess.CompletedProcess([],0,stdout='"user","invalid"\n')) as run:
            with self.assertRaises(RuntimeError):protect_directory(temporary)
            self.assertEqual(run.call_count,1)

    def test_acl_failure_or_timeout_never_succeeds(self):
        sid=subprocess.CompletedProcess([],0,stdout='"user","S-1-5-21-123"\n')
        for failure in (subprocess.CompletedProcess([],5),subprocess.TimeoutExpired('icacls',30)):
            with self.subTest(failure=type(failure).__name__),tempfile.TemporaryDirectory() as temporary,patch('ai_manager.external_process.run_external',side_effect=[sid,failure]):
                with self.assertRaises((RuntimeError,subprocess.TimeoutExpired)):protect_directory(temporary)

    def test_system_directory_failure_has_no_path_fallback(self):
        with tempfile.TemporaryDirectory() as temporary,patch('ai_manager.security._system_tool',side_effect=RuntimeError('Cannot identify Windows system directory')),patch('ai_manager.external_process.run_external') as run:
            with self.assertRaises(RuntimeError):protect_directory(temporary)
            run.assert_not_called()

    def test_system_api_zero_or_oversize_is_rejected(self):
        for length in (0,32768):
            with patch('ai_manager.security.ctypes.windll.kernel32.GetSystemDirectoryW',return_value=length):
                with self.assertRaises(RuntimeError):_system_tool('whoami.exe')

    def test_protected_populated_home_does_not_reapply_acl(self):
        sid=subprocess.CompletedProcess([],0,stdout='"user","S-1-5-21-123"\n')
        with tempfile.TemporaryDirectory() as temporary, patch('ai_manager.security.directory_is_private',return_value=True), patch('ai_manager.external_process.run_external',return_value=sid) as run:
            (Path(temporary)/'existing-data').write_bytes(b'preserve')
            protect_directory(temporary)
            self.assertEqual(run.call_count,1)
            self.assertEqual(Path(run.call_args.args[0][0]).name,'whoami.exe')
            self.assertEqual((Path(temporary)/'existing-data').read_bytes(),b'preserve')

    def test_unknown_populated_acl_is_not_rewritten(self):
        sid=subprocess.CompletedProcess([],0,stdout='"user","S-1-5-21-123"\n')
        for outcome in (False, OSError('read failed')):
            with self.subTest(outcome=type(outcome).__name__), tempfile.TemporaryDirectory() as temporary, patch('ai_manager.security.directory_is_private',side_effect=outcome if isinstance(outcome,Exception) else None,return_value=outcome), patch('ai_manager.external_process.run_external',return_value=sid) as run:
                (Path(temporary)/'existing-data').write_bytes(b'preserve')
                with self.assertRaises((RuntimeError,OSError)):protect_directory(temporary)
                self.assertEqual(run.call_count,1)

    def test_new_acl_requires_post_apply_verification(self):
        sid=subprocess.CompletedProcess([],0,stdout='"user","S-1-5-21-123"\n')
        with tempfile.TemporaryDirectory() as temporary, patch('ai_manager.security.directory_is_private',return_value=False), patch('ai_manager.external_process.run_external',side_effect=[sid,subprocess.CompletedProcess([],0)]) as run:
            with self.assertRaises(RuntimeError):protect_directory(Path(temporary)/'new')
            self.assertEqual(run.call_count,2)


class PrivateAclContract(unittest.TestCase):
    def test_exact_policy_and_negative_aces(self):
        sid='S-1-5-21-123'
        rules=[(sid,0,3,0x1F01FF),('S-1-5-18',0,3,0x1F01FF)]
        self.assertTrue(private_acl_contract(True,sid,rules,sid))
        bad=[rules+[('S-1-1-0',0,3,0x1F01FF)], [rules[0],('S-1-1-0',0,3,0x1F01FF)]]
        for index,value in ((1,1),(1,2),(2,19),(2,0),(3,0x120089)):
            changed=list(rules[0]);changed[index]=value;bad.append([tuple(changed),rules[1]])
        for value in bad:self.assertFalse(private_acl_contract(True,sid,value,sid))
        self.assertFalse(private_acl_contract(False,sid,rules,sid))
        self.assertFalse(private_acl_contract(True,'S-1-5-18',rules,sid))

if __name__=='__main__':unittest.main()
