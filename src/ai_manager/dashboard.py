"""Read-only views of this project's observations; no file bytes or model inference."""
import hashlib
import json
import re

from .inventory import Inventory


def family(path):
    value = path.casefold()
    for token, label in (("tts", "음성 합성"), ("whisper", "음성 인식"), ("qwen-asr", "음성 인식"), ("qwen-image", "이미지 생성"), ("qwen_image", "이미지 생성"), ("stable-diffusion", "이미지 생성"), ("flux", "이미지 생성"), ("llama", "언어 모델"), ("qwen", "언어 모델"), ("bert", "언어 모델")):
        if token in value:
            return label
    return "미분류"


def observations(files):
    names = [f["name"].casefold() for f in files]
    shards = {}
    for name in names:
        match = re.search(r"^(.*?)(\d+)-of-(\d+)(\.[^.]+)$", name)
        if match and len(match[2]) <= 9 and len(match[3]) <= 9:
            prefix, part, total, suffix = match.groups()
            key = (prefix, int(total), suffix)
            if 1 <= int(part) <= int(total):
                shards.setdefault(key, set()).add(int(part))
    missing = sum(total - len(parts) for (_, total, _), parts in shards.items())
    return {"weight_files": sum(f["kind"] == "weight_candidate" for f in files),
            "config_observed": any(n in {"config.json", "config.yaml", "config.yml", "configuration.json"} for n in names),
            "tokenizer_observed": any("tokenizer" in n or n.startswith("vocab.") for n in names),
            "shards_missing": missing if shards else None,
            "configuration": "unverified", "integrity": "unverified", "runtime": "unverified", "execution": "unverified"}


class Dashboard:
    def __init__(self, home):
        self.inventory = Inventory(home)

    def snapshot(self, scan=None):
        with self.inventory.connect() as db:
            if scan:
                rows = db.execute("SELECT * FROM scans WHERE scan_id=?", (scan,)).fetchall()
                if not rows:
                    raise ValueError("unknown scan")
            else:
                rows = db.execute("SELECT * FROM scans s WHERE scan_id=(SELECT scan_id FROM scans WHERE account=s.account ORDER BY started_at DESC,scan_id DESC LIMIT 1) ORDER BY account").fetchall()
            scans = [self.inventory._public(row) for row in rows]
            files = []
            for s in scans:
                for row in db.execute("SELECT * FROM files WHERE scan_id=? ORDER BY path,file_id", (s["scan_id"],)):
                    m = json.loads(row["metadata_json"])
                    raw_size = m.get("size")
                    size = int(raw_size) if str(raw_size).isdigit() else None
                    path = row["path"]
                    files.append({"id": hashlib.sha256((s["scan_id"] + row["file_id"]).encode()).hexdigest()[:24],
                                  "scan_id": s["scan_id"], "account": s["account"], "name": m.get("name", "미수집"), "path": path,
                                  "folder": path.rsplit("/", 1)[0], "root": row["root_alias"], "kind": row["kind"],
                                  "size": size, "modified": m.get("modifiedTime"), "format": m.get("name", "").rsplit(".", 1)[-1].lower(),
                                  "family": family(path), "scan_status": s["status"], "parent_identity": m.get("parents", [])})
        groups = {}
        for f in files:
            parents = f.pop("parent_identity")
            # Display paths are not identities: Drive permits duplicate folder names.
            identity = parents[0] if isinstance(parents, list) and len(parents) == 1 else "ambiguous:" + f["id"]
            key = f["account"] + ":" + identity
            if key not in groups:
                groups[key] = {"id": hashlib.sha256((f["scan_id"] + key).encode()).hexdigest()[:24], "name": f["folder"].rsplit("/", 1)[-1],
                               "path": f["folder"], "account": f["account"], "family": family(f["folder"]), "scan_id": f["scan_id"], "scan_status": f["scan_status"], "files": []}
            groups[key]["files"].append(f)
        models = []
        for group in groups.values():
            # A folder is only a grouping of observed candidates, never a verified model.
            group["count"] = len(group["files"])
            group["size"] = sum(f["size"] or 0 for f in group["files"]) if all(f["size"] is not None for f in group["files"]) else None
            group["observations"] = observations(group["files"])
            models.append(group)
        return {"scans": scans, "files": files, "models": models}

    def query(self, params):
        def arg(name, default=""):
            return params.get(name, [default])[0]
        view, account, category, task = arg("view", "models"), arg("account"), arg("kind"), arg("family")
        sort = arg("sort", "name")
        page, limit = int(arg("page", "1")), int(arg("limit", "24"))
        if view not in {"models", "files"} or account not in {"", "A", "B"} or sort not in {"name", "size", "modified"} or not 1 <= page or not 1 <= limit <= 100 or len(arg("q")) > 300:
            raise ValueError("invalid query")
        data = self.snapshot(arg("scan") or None)
        rows = data[view]
        q = arg("q").casefold().strip()
        filtered = [r for r in rows if (not account or r["account"] == account) and (not task or r["family"] == task)
                    and (not category or (r.get("kind") == category if view == "files" else any(f["kind"] == category for f in r["files"])))
                    and (not q or q in r["path"].casefold() or q in r["family"].casefold())]
        if sort == "size":
            filtered.sort(key=lambda r: (r["size"] is None, -(r["size"] or 0), r["path"].casefold(), r["id"]))
        elif sort == "modified":
            filtered.sort(key=lambda r: (r.get("modified") or max((f["modified"] or "" for f in r.get("files", [])), default=""), r["id"]), reverse=True)
        else:
            filtered.sort(key=lambda r: (r["name"].casefold(), r["account"], r["id"]))
        total = len(filtered)
        page = min(page, max(1, (total + limit - 1) // limit))
        result_rows = []
        for row in filtered[(page - 1) * limit:page * limit]:
            result_rows.append({k: v for k, v in row.items() if k != "files"})
        return {"rows": result_rows, "total": total, "page": page, "limit": limit, "scans": data["scans"],
                "summary": {"files": len(data["files"]), "groups": len(data["models"]), "weights": sum(f["kind"] == "weight_candidate" for f in data["files"]),
                            "known_bytes": sum(f["size"] or 0 for f in data["files"]), "unknown_sizes": sum(f["size"] is None for f in data["files"])},
                "families": sorted(set(r["family"] for r in rows))}

    def detail(self, identifier, scan=None):
        data = self.snapshot(scan)
        for row in data["models"] + data["files"]:
            if row["id"] == identifier:
                from .preparation import supported
                row["supports_preparation"] = supported(row)
                return row
        raise KeyError("not found")
