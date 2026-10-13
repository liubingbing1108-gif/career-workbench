"""Scoped profile feasibility lab. No recruiting site or production data connector."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import logging
import re
import sqlite3
import threading
import uuid
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree


CATEGORIES = [
    ("basic", "基本身份", False), ("contact", "联系与地址", False),
    ("education", "教育经历", True), ("language", "语言能力", True),
    ("skills", "技能", True), ("honors", "荣誉与奖励", True),
    ("academic", "学术成果", True), ("certificates", "资格与证书", True),
    ("employment", "实习与工作", True), ("projects", "项目与研究", True),
    ("campus", "校园与社会经历", True), ("subjective", "主观文本", False),
    ("family", "家庭与联系人", True), ("preferences", "求职相关信息", False),
    ("portfolio", "作品", True), ("social", "社交账号", True),
    ("attachments", "附件", False), ("additional", "官网新增字段", False),
]
SAMPLE_FIELDS = [
    ("name", "姓名", "basic", "text", ["Name"]),
    ("phone", "手机", "contact", "text", ["Phone", "手机号", "电话"]),
    ("email", "邮箱", "contact", "text", ["Email", "电子邮箱"]),
    ("school", "学校", "education", "text", ["School"]),
    ("major", "专业", "education", "text", ["Major"]),
    ("degree", "学历", "education", "text", ["Degree"]),
    ("graduation_date", "毕业日期", "education", "date", ["Graduation date"]),
    ("company", "公司", "employment", "text", ["Company", "单位"]),
    ("role", "职位", "employment", "text", ["Role"]),
    ("employment_type", "经历性质", "employment", "text", ["Employment type"]),
    ("started", "开始日期", "employment", "date", ["Start date"]),
    ("ended", "结束日期", "employment", "date", ["End date"]),
    ("description", "经历描述", "employment", "versioned_text", ["Description"]),
]
IDENTITY_FIELDS = {
    "education": ["school", "major", "degree", "graduation_date"],
    "employment": ["company", "role", "employment_type", "started", "ended"],
}
KINDS = {"text", "multiline", "date", "partial_date", "number", "select", "versioned_text"}


class LabError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex[:12]


def category(category_id):
    return next((x for x in CATEGORIES if x[0] == category_id), None)


def initial_state():
    return {
        "categories": [{"id": k, "label": v, "repeatable": r} for k, v, r in CATEGORIES],
        "fields": [{"id": k, "label": v, "category": c, "type": t,
                    "aliases": aliases, "options": []} for k, v, c, t, aliases in SAMPLE_FIELDS],
        "entries": [{"id": uid(k), "category": k, "values": {}, "sources": {}}
                    for k, _, repeatable in CATEGORIES if not repeatable],
        "versions": [], "files": [], "imports": [], "sessions": [],
    }


def find(items, item_id, message="记录不存在"):
    item = next((x for x in items if x["id"] == item_id), None)
    if item is None:
        raise LabError(message, 404)
    return item


def validate_value(field, value):
    if not isinstance(value, str) or len(value) > 30000:
        raise LabError("字段值必须为文本，且不能超过 30000 字符")
    if value and field["type"] == "date":
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except ValueError:
            raise LabError(f'{field["label"]}需要有效的 YYYY-MM-DD 日期')
    if value and field["type"] == "number":
        if not re.fullmatch(r"-?\d+(\.\d+)?", value):
            raise LabError(f'{field["label"]}需要数字')
    if value and field["type"] == "partial_date":
        if value != "至今":
            if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
                raise LabError(f'{field["label"]}需要 YYYY、YYYY-MM、YYYY-MM-DD 或至今')
            try:
                date.fromisoformat(value + ("-01-01" if len(value) == 4 else "-01" if len(value) == 7 else ""))
            except ValueError:
                raise LabError(f'{field["label"]}日期无效')
    if value and field["type"] == "select" and value not in field["options"]:
        raise LabError(f'{field["label"]}不在该字段的选项中')
    return value


def extract_text(filename, raw):
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        try:
            return [{"text": raw.decode("utf-8-sig"), "location": "文本文件"}]
        except UnicodeDecodeError:
            raise LabError("示例 TXT 需要 UTF-8 编码")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = ["word/document.xml"] + sorted(n for n in archive.namelist() if re.fullmatch(r"word/(?:header|footer)\d+\.xml", n))
                if sum(archive.getinfo(n).file_size for n in names) > 8 * 1024 * 1024:
                    raise LabError("文档正文过大")
                roots = [(n, ElementTree.fromstring(archive.read(n))) for n in names]
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            blocks = []
            def paragraph_text(para):
                pieces = []
                def visit(node):
                    for child in node:
                        if child.tag == f'{{{ns["w"]}}}p':
                            continue  # Nested text boxes are extracted as their own paragraphs.
                        if child.tag == f'{{{ns["w"]}}}t':
                            pieces.append(child.text or "")
                        elif child.tag in {f'{{{ns["w"]}}}br', f'{{{ns["w"]}}}tab'}:
                            pieces.append("\n" if child.tag.endswith("}br") else "\t")
                        else:
                            visit(child)
                visit(para)
                return "".join(pieces)
            for name, root in roots:
                prefix = "段落" if name == "word/document.xml" else "页眉" if "/header" in name else "页脚"
                for number, para in enumerate(root.findall(".//w:p", ns), 1):
                    text = paragraph_text(para)
                    if text.strip():
                        blocks.append({"text": text, "location": f"{prefix} {number}"})
            return blocks
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
            raise LabError("无法读取 DOCX 正文")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            logging.getLogger("pypdf").setLevel(logging.ERROR)
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise LabError("加密 PDF 需要先由用户解密")
            if len(reader.pages) > 50:
                raise LabError("验证页最多读取 50 页")
            return [{"text": p.extract_text() or "", "location": f"第 {i} 页"}
                    for i, p in enumerate(reader.pages, 1)]
        except ImportError:
            raise LabError("当前运行环境缺少 pypdf，请使用 README 中的 Python 启动")
        except LabError:
            raise
        except Exception:
            raise LabError("无法读取 PDF 正文")
    raise LabError("验证页支持 PDF、DOCX 和 UTF-8 TXT")


def parse_sample_fields(state, blocks, filename):
    """Transparent labelled-sample extractor; never a claimed semantic model."""
    aliases = {}
    for field in state["fields"]:
        for label in [field["label"], *field.get("aliases", [])]:
            aliases.setdefault(label.casefold(), []).append(field)
    groups, indices = {}, {}
    for block in blocks:
        for line in block["text"].splitlines():
            matched = re.match(r"^\s*([^:：]+)\s*[:：]\s*(.*?)\s*$", line)
            if not matched:
                continue
            label, value = matched.groups()
            fields = aliases.get(label.strip().casefold(), [])
            if len(fields) != 1 or not value:
                continue
            field = fields[0]
            cat = field["category"]
            index = indices.get(cat, 0)
            group_id = f"{cat}:{index}"
            if category(cat)[2] and field["id"] in groups.get(group_id, {}):
                index += 1
                indices[cat] = index
                group_id = f"{cat}:{index}"
            groups.setdefault(group_id, {})[field["id"]] = {
                "value": value, "source": {"filename": filename,
                    "location": block["location"], "quote": line.strip()},
            }
    candidates = []
    for group_id, fields in groups.items():
        cat = group_id.split(":")[0]
        entries = [e for e in state["entries"] if e["category"] == cat]
        target = entries[0] if not category(cat)[2] else None
        identity = IDENTITY_FIELDS.get(cat, [])
        if identity and all(k in fields for k in identity):
            matches = [e for e in entries if all(e["values"].get(k) == fields[k]["value"] for k in identity)]
            target = matches[0] if len(matches) == 1 else None
        for field_id, item in fields.items():
            field = find(state["fields"], field_id)
            existing = target["values"].get(field_id, "") if target else ""
            status = "一致" if existing == item["value"] else "事实冲突" if existing else "新增"
            if field["type"] == "versioned_text":
                versions = [v for v in state["versions"] if target and v["entry_id"] == target["id"] and v["field_id"] == field_id]
                status = "一致" if any(v["content"] == item["value"] for v in versions) else "描述待检查" if versions else "新增描述"
            try:
                validate_value(field, item["value"])
                valid = True
            except LabError:
                status, valid = "需更正格式", False
            candidates.append({"id": uid("candidate"), "field_id": field_id,
                "category": cat, "group": group_id, "entry_id": target["id"] if target else None,
                "label": field["label"], "type": field["type"], "value": item["value"],
                "existing": existing, "status": status, "saved": False,
                "selected": valid and status in {"新增", "新增描述"}, "source": item["source"]})
    return candidates


def finish_preview(state, import_id, candidates, warnings, usage):
    preview = find(state["imports"], import_id)
    preview.update(candidates=candidates, warnings=warnings, usage=usage, status="完成", error="")
    return preview


ANCHORS = {"education": ["school", "major", "education_started", "graduation_date"],
           "employment": ["company", "started"], "language": ["language_name"],
           "skills": ["skill_name"], "certificates": ["certificate_name"],
           "honors": ["award_name"], "campus": ["campus_title"], "projects": ["project_name"]}


def identity_key(cat, values):
    from recognizer import compact
    anchors = ANCHORS.get(cat, [])
    if cat == "education" and not values.get("education_started"):
        anchors = ["school", "major", "graduation_date"]
    if not anchors or not all(values.get(k) for k in anchors):
        return None
    def normalize(key, value):
        value = compact(value)
        if key == "major":
            value = re.sub(r"专业$", "", value)
        return value
    return cat + ":" + json.dumps([normalize(k, values[k]) for k in anchors], ensure_ascii=False)


def all_versions(state, entry_id, field_id):
    return [v for store in ("versions", "answer_versions") for v in state.get(store, [])
            if v["entry_id"] == entry_id and v["field_id"] == field_id]


def default_version(state, entry, field_id):
    versions = all_versions(state, entry["id"], field_id)
    return next((v for v in versions if v["id"] == entry.get("default_versions", {}).get(field_id)), versions[0] if versions else None)


def put_answer(state, entry, field, content, mode="new", target_id=None, name="新版本", source=None):
    from recognizer import compact
    content = validate_value(field, content)
    store = state["versions" if field["type"] == "versioned_text" else "answer_versions"]
    versions = all_versions(state, entry["id"], field["id"])
    if mode == "replace" and versions:
        target = find(versions, target_id) if target_id else default_version(state, entry, field["id"])
        target.update(content=content, revision=target["revision"] + 1, source=source or {"kind": "manual"})
    else:
        target = next((v for v in versions if compact(v["content"]) == compact(content)), None)
        if target is None:
            target = {"id": uid("version"), "entry_id": entry["id"], "field_id": field["id"],
                      "content": content, "name": name[:180], "revision": 1, "source": source or {"kind": "manual"}}
            store.append(target)
    entry.setdefault("default_versions", {}).setdefault(field["id"], target["id"])
    current = default_version(state, entry, field["id"])
    if field["type"] != "versioned_text":
        entry["values"][field["id"]] = current["content"]
        entry["sources"][field["id"]] = current.get("source", {})
    return target


def candidate_pending(c):
    return not c.get("saved") and c.get("disposition") != "ignore" and c.get("status") not in {"一致", "已忽略", "已合并"}


def reconcile_semantic_imports(state):
    """One incremental decision per known identity/field/value; never reconfirm facts."""
    from recognizer import compact
    state.setdefault("ignored_candidates", [])
    grouped, signatures = {}, {}
    for preview in state["imports"]:
        signatures[preview["id"]] = [(c.get("entry_id"), c.get("existing"), c.get("status"), c.get("duplicate_of")) for c in preview["candidates"]]
        local = {}
        for c in preview["candidates"]:
            local.setdefault(c["group"], []).append(c)
        for group, rows in local.items():
            cat = rows[0]["category"]
            key = identity_key(cat, {c["field_id"]: c["value"] for c in rows}) if category(cat)[2] else cat
            prior_id = next((c.get("created_entry") or c.get("entry_id") for c in rows if c.get("saved") or not preview.get("semantic")), None)
            if not key and prior_id:
                entry = next((e for e in state["entries"] if e["id"] == prior_id), None)
                key = entry.get("identity_key") or identity_key(cat, entry["values"]) if entry else None
            key = key or preview["id"] + "/" + group
            for c in rows:
                c["identity_key"] = key
                c["import_id"] = preview["id"]
            grouped.setdefault(key, []).extend(rows)
    for key, rows in grouped.items():
        cat = rows[0]["category"]
        entries = [e for e in state["entries"] if e["category"] == cat]
        if category(cat)[2]:
            matches = [e for e in entries if e.get("identity_key") == key or identity_key(cat, e["values"]) == key]
            prior = {c.get("created_entry") for c in rows if c.get("created_entry")}
            if not matches and len(prior) == 1:
                matches = [e for e in entries if e["id"] in prior]
            target = matches[0] if len(matches) == 1 else None
        else:
            target = entries[0] if entries else None
        canonical = {}
        for c in rows:
            c["fingerprint"] = hashlib.sha256((key + "/" + c["field_id"] + "/" + compact(c["value"])).encode()).hexdigest()
            versions = all_versions(state, target["id"], c["field_id"]) if target else []
            current = default_version(state, target, c["field_id"]) if target else None
            c["existing_versions"] = copy.deepcopy(versions)
            c["default_version_id"] = current["id"] if current else None
            c["duplicate_of"] = None
            if c.get("saved"):
                continue
            c["entry_id"] = target["id"] if target else None
            c["existing"] = current["content"] if current else (target["values"].get(c["field_id"], "") if target else "")
            if c.get("disposition") == "same":
                c["status"], c["selected"] = "一致", False
                continue
            if c.get("disposition") == "ignore" or c["fingerprint"] in state["ignored_candidates"]:
                c["status"], c["selected"] = "已忽略", False
                continue
            same = any(compact(v["content"]) == compact(c["value"]) for v in versions)
            if not versions and c["existing"]:
                same = compact(c["existing"]) == compact(c["value"])
            if same:
                c["status"], c["selected"], c["disposition"] = "一致", False, "same"
                continue
            fingerprint = c["fingerprint"]
            if fingerprint in canonical:
                c["status"], c["selected"], c["duplicate_of"] = "已合并", False, canonical[fingerprint]["id"]
                canonical[fingerprint].setdefault("other_sources", []).append(c["source"])
                continue
            c["other_sources"] = []
            canonical[fingerprint] = c
            alternatives = {compact(r["value"]) for r in rows if r["field_id"] == c["field_id"] and not r.get("saved") and r.get("disposition") != "ignore"}
            c["status"] = "描述待检查" if versions and c["type"] == "versioned_text" else "事实冲突" if versions or (len(alternatives) > 1 and c["type"] != "versioned_text") else "新增描述" if c["type"] == "versioned_text" else "新增"
            c["selected"] = c["status"] in {"新增", "新增描述"}
            field = next((f for f in state["fields"] if f["id"] == c["field_id"]), c.get("definition", {"label": c["label"], "type": c["type"]}))
            try:
                validate_value(field, c["value"])
            except LabError:
                c["status"], c["selected"] = "需更正格式", False
    for preview in state["imports"]:
        changed = signatures[preview["id"]] != [(c.get("entry_id"), c.get("existing"), c.get("status"), c.get("duplicate_of")) for c in preview["candidates"]]
        preview["revision"] = preview.get("revision", 1) + int(changed)


class Lab:
    def __init__(self, directory, recognizer=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.recognizer = recognizer
        self.db = sqlite3.connect(self.directory / "lab.sqlite", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, body BLOB NOT NULL)")
        if not self.db.execute("SELECT 1 FROM state WHERE id=1").fetchone():
            self.db.execute("INSERT INTO state VALUES (1,?)", (json.dumps(initial_state(), ensure_ascii=False),))
        self.db.commit()
        # Widen date precision without changing any previously recorded value.
        def migrate(state):
            state.setdefault("answer_versions", [])
            for key, label, repeatable in CATEGORIES:
                if not any(c['id'] == key for c in state['categories']):
                    state['categories'].append({'id': key, 'label': label, 'repeatable': repeatable})
            for field in state["fields"]:
                if field["id"] in {"started", "ended", "graduation_date"} and field["type"] == "date":
                    field["type"] = "partial_date"
            for entry in state["entries"]:
                entry.setdefault("default_versions", {})
                for field_id, value in entry["values"].items():
                    field = next((f for f in state["fields"] if f["id"] == field_id), None)
                    if field and not all_versions(state, entry["id"], field_id):
                        put_answer(state, entry, field, value, name="已确认版本", source=entry["sources"].get(field_id))
                for version in state["versions"]:
                    if version["entry_id"] == entry["id"]:
                        entry["default_versions"].setdefault(version["field_id"], version["id"])
            if state.get("profile_schema_version", 0) < 3:
                # Older prototype overwrote scalar answers during explicit imports.
                # Recover those confirmed alternatives from their retained provenance,
                # while keeping the user's latest value as the default.
                for preview in state["imports"]:
                    for c in preview["candidates"]:
                        if not c.get("saved") or c["type"] == "versioned_text":
                            continue
                        entry_id = c.get("created_entry") or c.get("entry_id")
                        entry = next((e for e in state["entries"] if e["id"] == entry_id), None)
                        field = next((f for f in state["fields"] if f["id"] == c["field_id"]), None)
                        if entry and field:
                            put_answer(state, entry, field, c["value"], name=preview["filename"], source=c["source"])
            state["profile_schema_version"] = 3
        self.mutate(migrate)

    def state(self):
        with self.lock:
            return json.loads(self.db.execute("SELECT body FROM state WHERE id=1").fetchone()[0])

    def mutate(self, action):
        with self.lock, self.db:
            state = self.state()
            result = action(state)
            reconcile_semantic_imports(state)
            self.db.execute("UPDATE state SET body=? WHERE id=1", (json.dumps(state, ensure_ascii=False),))
            return copy.deepcopy(result)

    def upload(self, filename, raw):
        filename = Path(filename.replace("\\", "/")).name
        if not filename or len(filename) > 180 or not raw or len(raw) > 8 * 1024 * 1024:
            raise LabError("文件名无效或文件超过 8 MiB")
        blocks = extract_text(filename, raw)
        if sum(len(b["text"]) for b in blocks) > 80000:
            raise LabError("文档正文超过本轮识别的 80000 字符限制")
        def save(state):
            file_id = uid("file")
            self.db.execute("INSERT INTO files VALUES (?,?)", (file_id, raw))
            state["files"].append({"id": file_id, "name": filename, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            preview = {"id": uid("import"), "file_id": file_id, "filename": filename,
                "extractor": self.recognizer.name if self.recognizer else "带标签示例解析（测试模式）",
                "candidates": [] if self.recognizer else parse_sample_fields(state, blocks, filename),
                "semantic": bool(self.recognizer), "status": "识别中" if self.recognizer else "完成",
                "readable": any(b["text"].strip() for b in blocks)}
            state["imports"].append(preview)
            return preview
        preview = self.mutate(save)
        if self.recognizer:
            return self.recognize_import(preview["id"], blocks)
        return preview

    def recognition_status(self):
        return self.recognizer.status() if self.recognizer else {"engine": "带标签示例解析（测试模式）", "available": True, "ocr": False}

    def recognize_import(self, import_id, blocks=None):
        from recognizer import grounded_candidates, RecognitionError
        if not self.recognizer:
            raise LabError("当前为示例测试模式")
        preview = find(self.state()["imports"], import_id)
        if any(c["saved"] for c in preview["candidates"]):
            raise LabError("已有资料已保存，请重新上传建立新预览")
        if blocks is None:
            meta, raw = self.file_bytes(preview["file_id"])
            blocks = extract_text(meta["name"], raw)
        self.mutate(lambda s: find(s["imports"], import_id).update(status="识别中", error=""))
        if not any(b["text"].strip() for b in blocks):
            return self.mutate(lambda s: finish_preview(s, import_id, [], ["未读取到文字层；扫描 PDF 尚未接入 OCR，可以上传文字版或手填资料。"], {}))
        try:
            result, usage = self.recognizer.extract(self.state()["fields"], blocks)
            # Keep the model draft only in this temporary application session so
            # deterministic validation can be repaired without resending a resume.
            self.mutate(lambda s: find(s["imports"], import_id).update(model_result=result))
            candidates, rejected = grounded_candidates(self.state(), blocks, preview["filename"], result)
            warnings = [str(w)[:500] for w in result.get("warnings", [])][:30] + rejected
            self.mutate(lambda s: finish_preview(s, import_id, candidates, warnings, usage))
            return find(self.state()["imports"], import_id)
        except RecognitionError as error:
            self.mutate(lambda s: find(s["imports"], import_id).update(status="失败", error=str(error)))
            raise LabError(str(error), 502)

    def revalidate_import(self, import_id):
        from recognizer import grounded_candidates, RecognitionError
        preview = find(self.state()["imports"], import_id)
        if any(c["saved"] for c in preview["candidates"]):
            raise LabError("已有资料已保存，不能替换此预览")
        if not preview.get("model_result"):
            raise LabError("此旧预览没有模型草稿，请重新识别")
        meta, raw = self.file_bytes(preview["file_id"])
        blocks = extract_text(meta["name"], raw)
        try:
            candidates, rejected = grounded_candidates(self.state(), blocks, preview["filename"], preview["model_result"])
        except RecognitionError as error:
            raise LabError(str(error))
        self.mutate(lambda s: finish_preview(s, import_id, candidates, preview["model_result"].get("warnings", []) + rejected, preview.get("usage", {})))
        return find(self.state()["imports"], import_id)

    def file_bytes(self, file_id):
        with self.lock:
            meta = find(self.state()["files"], file_id)
            return meta, bytes(self.db.execute("SELECT body FROM files WHERE id=?", (file_id,)).fetchone()[0])

    def commit_import(self, import_id, accepted, edits, expected_revision=None):
        # Compatibility API: ordinary save creates an additional answer, never overwrites.
        decisions = [{"candidate_id": cid, "mode": "new", "value": edits.get(cid)} for cid in accepted]
        result = self.resolve_import(decisions, {import_id: expected_revision} if expected_revision is not None else {})
        preview = find(self.state()["imports"], import_id)
        return {"saved": result["saved"], "pending": sum(candidate_pending(c) for c in preview["candidates"])}

    def increments(self):
        state = self.state()
        candidates = [c for p in state["imports"] for c in p["candidates"] if candidate_pending(c)]
        return {"candidates": candidates, "revisions": {p["id"]: p.get("revision", 1) for p in state["imports"]},
                "consistent": sum(c.get("status") == "一致" for p in state["imports"] for c in p["candidates"]),
                "merged": sum(c.get("status") == "已合并" for p in state["imports"] for c in p["candidates"])}

    def resolve_import(self, decisions, revisions=None):
        def commit(state):
            for pid, revision in (revisions or {}).items():
                if revision != find(state["imports"], pid).get("revision", 1):
                    raise LabError("资料已更新，请重新打开增量预览", 409)
            rows = {c["id"]: (p, c) for p in state["imports"] for c in p["candidates"]}
            groups, saved, ignored = {}, 0, 0
            if len({d["candidate_id"] for d in decisions}) != len(decisions):
                raise LabError("同一增量不能重复处理")
            for decision in decisions:
                if decision["candidate_id"] not in rows:
                    raise LabError("增量记录不存在")
                preview, candidate = rows[decision["candidate_id"]]
                mode = decision["mode"]
                if mode not in {"replace", "new", "ignore"}:
                    raise LabError("请选择替换、新版本或忽略")
                if not candidate_pending(candidate):
                    continue
                if mode == "ignore":
                    candidate["disposition"] = "ignore"
                    state["ignored_candidates"].append(candidate["fingerprint"])
                    ignored += 1
                    continue
                field = next((f for f in state["fields"] if f["id"] == candidate["field_id"]), None)
                if field is None:
                    field = copy.deepcopy(candidate["definition"])
                    if any(f["category"] == field["category"] and f["label"] == field["label"] for f in state["fields"]):
                        raise LabError("新增字段名称已存在，请刷新预览", 409)
                    state["fields"].append(field)
                value = validate_value(field, decision.get("value") if decision.get("value") is not None else candidate["value"])
                key = candidate["identity_key"]
                if candidate.get("entry_id"):
                    entry = find(state["entries"], candidate["entry_id"])
                    current = default_version(state, entry, field["id"])
                    if not revisions and field["type"] != "versioned_text" and (current["content"] if current else entry["values"].get(field["id"], "")) != candidate["existing"]:
                        raise LabError("底稿已更新，请刷新预览", 409)
                else:
                    entry = groups.get(key)
                    if entry is None:
                        entry = next((e for e in state["entries"] if e.get("identity_key") == key), None) or self.new_entry(state, field["category"])
                        entry["identity_key"] = key
                        groups[key] = entry
                    for p in state["imports"]:
                        for c in p["candidates"]:
                            if c.get("identity_key") == key:
                                c["created_entry"] = entry["id"]
                put_answer(state, entry, field, value, mode, decision.get("version_id"), preview["filename"], candidate["source"])
                candidate["saved"], candidate["disposition"] = True, mode
                saved += 1
            return {"saved": saved, "ignored": ignored}
        return self.mutate(commit)

    @staticmethod
    def new_entry(state, cat):
        if not category(cat):
            raise LabError("未知资料分类")
        existing = [e for e in state["entries"] if e["category"] == cat]
        if existing and not category(cat)[2]:
            return existing[0]
        entry = {"id": uid(cat), "category": cat, "values": {}, "sources": {}}
        state["entries"].append(entry)
        return entry

    def add_field(self, request):
        def add(state):
            label = request.get("label", "").strip()
            cat, kind = request.get("category"), request.get("type", "text")
            if not label or len(label) > 100 or not category(cat) or kind not in KINDS:
                raise LabError("字段名称、分类或类型无效")
            field_id = request.get("id") or uid("custom")
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", field_id):
                raise LabError("字段标识无效")
            if any(f["id"] == field_id or (f["category"] == cat and f["label"] == label) for f in state["fields"]):
                raise LabError("字段已存在", 409)
            options = request.get("options", [])
            if not isinstance(options, list) or any(not isinstance(x, str) or not x for x in options) or (kind == "select" and not options):
                raise LabError("选择字段需要有效选项")
            field = {"id": field_id, "label": label, "category": cat, "type": kind, "aliases": [], "options": options}
            state["fields"].append(field)
            return field
        return self.mutate(add)

    def save_profile(self, values):
        def save(state):
            for patch in values:
                field = find(state["fields"], patch["field_id"])
                entry = find(state["entries"], patch["entry_id"])
                if entry["category"] != field["category"] or field["type"] == "versioned_text":
                    raise LabError("字段不属于此条资料或应通过描述版本编辑")
                put_answer(state, entry, field, patch["value"], mode="replace", name="手填版本")
            return {"saved": len(values)}
        return self.mutate(save)

    def create_version(self, entry_id, field_id, content, name="手填描述"):
        def create(state):
            field = find(state["fields"], field_id)
            entry = find(state["entries"], entry_id)
            if field["category"] != entry["category"]:
                raise LabError("版本不属于该字段或资料条目")
            return put_answer(state, entry, field, content, name=name)
        return self.mutate(create)

    def set_default(self, entry_id, field_id, version_id):
        def update(state):
            entry = find(state["entries"], entry_id)
            field = find(state["fields"], field_id)
            version = find(all_versions(state, entry_id, field_id), version_id)
            entry.setdefault("default_versions", {})[field_id] = version_id
            if field["type"] != "versioned_text":
                entry["values"][field_id], entry["sources"][field_id] = version["content"], version["source"]
            return version
        return self.mutate(update)

    def new_session(self, name="新投递演练"):
        def add(state):
            session = {"id": uid("session"), "name": name[:80], "overrides": {}, "selected_versions": {}}
            state["sessions"].append(session)
            return session
        return self.mutate(add)

    def answer(self, session_id, field_id, value, save_to_profile=False):
        def save(state):
            session = find(state["sessions"], session_id)
            field = find(state["fields"], field_id)
            if field["type"] == "versioned_text" or category(field["category"])[2]:
                raise LabError("此示例补充入口用于单项字段，多条经历由全表单维护")
            value_checked = validate_value(field, value)
            session["overrides"][field_id] = value_checked
            if save_to_profile:
                entry = self.new_entry(state, field["category"])
                put_answer(state, entry, field, value_checked, mode="replace", source={"kind": "manual", "from_session": session_id})
                session["overrides"].pop(field_id, None)
            return {"saved_to_profile": bool(save_to_profile)}
        return self.mutate(save)

    def edit_version(self, session_id, version_id, mode, content, expected_revision=None, name=""):
        def edit(state):
            session = find(state["sessions"], session_id)
            version = find(state["versions"] + state["answer_versions"], version_id)
            field = find(state["fields"], version["field_id"])
            validate_value(field, content)
            key = version["entry_id"] + "/" + version["field_id"]
            if mode == "update":
                if expected_revision != version["revision"]:
                    raise LabError("此版本已经更新，请刷新后重新编辑", 409)
                version["content"] = content
                version["revision"] += 1
                version["source"] = {"kind": "manual"}
                entry = find(state["entries"], version["entry_id"])
                if field["type"] != "versioned_text" and default_version(state, entry, field["id"])["id"] == version_id:
                    entry["values"][field["id"]] = content
                    entry["sources"][field["id"]] = version["source"]
                session["selected_versions"][key] = version["id"]
                session["overrides"].pop(key, None)
            elif mode == "new":
                version = {**version, "id": uid("version"), "name": name.strip()[:100] or "新描述版本",
                           "content": content, "revision": 1, "source": {"kind": "manual"}}
                state["versions" if field["type"] == "versioned_text" else "answer_versions"].append(version)
                session["selected_versions"][key] = version["id"]
                session["overrides"].pop(key, None)
            elif mode == "session":
                session["selected_versions"][key] = version["id"]
                session["overrides"][key] = content
            else:
                raise LabError("未知版本保存方式")
            if mode in {"update", "new"} and not category(field["category"])[2]:
                session["overrides"].pop(field["id"], None)
            return {"version": version, "mode": mode}
        return self.mutate(edit)

    def select_version(self, session_id, version_id):
        def select(state):
            session = find(state["sessions"], session_id)
            version = find(state["versions"] + state["answer_versions"], version_id)
            key = version["entry_id"] + "/" + version["field_id"]
            session["selected_versions"][key] = version_id
            session["overrides"].pop(key, None)
            return session
        return self.mutate(select)

    def materials(self, session_id):
        from application import entry_material
        state = self.state()
        session = find(state["sessions"], session_id)
        grouped, values, sources, version_choices = {}, {}, {}, []
        for cat in state["categories"]:
            entries = [e for e in state["entries"] if e["category"] == cat["id"]]
            if cat["id"] in session.get("selected_entries", {}):
                selected_ids = session["selected_entries"][cat["id"]]
                entries = [find(entries, eid) for eid in selected_ids]
            items = [entry_material(state, session, e) for e in entries]
            grouped[cat["id"]] = items
            # A flat view exists only when a category has one unambiguous entry.
            # Repeated materials remain arrays; no first-entry shortcut is used.
            if len(items) == 1:
                values.update(items[0]["values"])
                for choice in items[0]["choices"]:
                    sources[choice["field"]["id"]] = "本次选择或已确认默认资料"
            for item in items:
                for choice in item["choices"]:
                    if choice["field"]["type"] == "versioned_text" and choice["selected"]:
                        version_choices.append({"field_id":choice["field"]["id"], "entry_id":item["id"],
                            "selected":choice["selected"], "versions":choice["versions"], "content":choice["content"]})
        return {"values":values, "sources":sources, "versions":version_choices, "entries":grouped, "session":session}
