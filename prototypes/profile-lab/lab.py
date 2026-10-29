"""Scoped profile feasibility lab. No recruiting site or production data connector."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
import sqlite3
import threading
import time
import uuid
from datetime import date
from pathlib import Path


CATEGORIES = [
    ("basic", "基本身份", False), ("contact", "联系与地址", False),
    ("education", "教育经历", True), ("language", "语言能力", True),
    ("skills", "技能", True), ("honors", "荣誉与奖励", True),
    ("academic", "学术成果", True), ("certificates", "资格与证书", True),
    ("employment", "实习与工作", True), ("projects", "项目与研究", True),
    ("campus", "校园与社会经历", True), ("subjective", "个人陈述", True),
    ("family", "家庭与联系人", True), ("preferences", "求职意向", True),
    ("portfolio", "作品", True), ("social", "社交账号", True),
    ("identity_documents", "身份证件", True), ("attachments", "文件附件", False), ("additional", "官网新增字段", False),
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
        "entries": [{"id": uid(k), "category": k, "values": {}, "sources": {}, "default_versions": {}}
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
    if field.get("widget")=="boolean" and value not in ("","是","否","不适用"):
        raise LabError(field["label"]+"请选择是、否、未提供或不适用")
    if field.get('boolean_values') and value not in ['', *field['boolean_values']]:
        raise LabError(field['label']+'请选择是、否或留空')
    if value and field["type"] == "date":
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except ValueError:
            raise LabError(f'{field["label"]}需要有效的 YYYY-MM-DD 日期')
    if value and field["type"] == "number":
        if not re.fullmatch(r"-?\d+(\.\d+)?", value):
            raise LabError(f'{field["label"]}需要数字')
        if field.get('integer') and not re.fullmatch(r'\d+', value):
            raise LabError(f'{field["label"]}需要非负整数')
    if field.get('widget') == 'multi_select' and value:
        chosen=value.split('\n')
        if len(chosen)!=len(set(chosen)) or set(chosen)-set(field.get('options',[])):
            raise LabError(field['label']+'包含无效选项')
    if field.get('widget') == 'exam_components' and value:
        from decimal import Decimal, InvalidOperation
        try:
            rows=json.loads(value)
            if not isinstance(rows,list) or len(rows)>100:raise ValueError()
            for row in rows:
                if not isinstance(row,dict) or set(row)-{'name','score','scale'}:raise ValueError()
                if not all(isinstance(v,str) and len(v)<=500 for v in row.values()):raise ValueError()
                for key in ('score','scale'):
                    if row.get(key) and not Decimal(row[key]).is_finite():raise ValueError()
        except (ValueError, TypeError, InvalidOperation):
            raise LabError('分项成绩需要项目名称、数字成绩和分制组成的列表')
    if value and field["type"] == "partial_date":
        if value != "至今" and value not in field.get('date_markers',[]):
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
    from document_markdown import convert_document
    return convert_document(filename, raw)


def conversion_metadata(blocks):
    return dict(converter='MarkItDown', conversion_format='markdown', document_blocks=blocks,
                text_preview='\n'.join(b['text'] for b in blocks)[:16000],
                readable=any(b['text'].strip() for b in blocks))


def parse_sample_fields(state, blocks, filename):
    """Transparent labelled-sample extractor; never a claimed semantic model."""
    aliases = {}
    for field in state["fields"]:
        for label in [field["label"], *field.get("aliases", [])]:
            bucket=aliases.setdefault(label.casefold(), [])
            if field not in bucket:bucket.append(field)
    groups, indices = {}, {}
    for block in blocks:
        for line in block["text"].splitlines():
            matched = re.match(r"^\s*([^:：]+)\s*[:：]\s*(.*?)\s*$", line)
            if not matched:
                continue
            label, value = matched.groups()
            fields = aliases.get(label.strip().casefold(), [])
            if len(fields)>1:
                sample_ids={k for k,l,c,t,names in SAMPLE_FIELDS if label.strip().casefold() in {n.casefold() for n in [l,*names]}}
                fields=[f for f in fields if f["id"] in sample_ids]
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
    if usage.get('parser_contract'):
        preview['parser_contract']=usage['parser_contract']
        from resume_import import groups, comparison_token
        ignored=set(preview.get('ignored_groups',[]))
        for rows in groups(candidates).values():
            if comparison_token({c['field_id']:c['value'] for c in rows}) in ignored:
                for c in rows:c.update(disposition='ignore',status='已忽略',selected=False)
    previous_candidates=copy.deepcopy(preview.get("candidates",[]))
    preview.update(candidates=candidates, warnings=warnings, usage=usage, status="完成", stage="完成", error="", finished_at=time.time())
    if usage.get("review_contract"):
        preview["review_contract"]=usage["review_contract"]
        from import_questions import build_questions
        build_questions(state,preview,previous_candidates)
        preview["stage"]="完成识别确认" if preview.get("review_completed") else "识别内容已就绪，待确认（可跳过）"
    return preview


ANCHORS = {"education": ["school", "major", "education_started", "graduation_date"],
           "employment": ["company", "role", "started", "ended"], "language": ["language_name"],
           "skills": ["skill_name"], "certificates": ["certificate_name"],
           "honors": ["award_name", "award_date"], "campus": ["campus_title"], "projects": ["project_name"]}


def identity_key(cat, values):
    from recognizer import compact
    anchors = ANCHORS.get(cat, [])
    if cat == "language" and (values.get("exam_name") or values.get("language_score")):
        anchors = ["exam_name", "exam_date"]
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
    versions = [v for v in all_versions(state, entry["id"], field_id) if not v.get('profile_deleted')]
    from profile_contract import active, expression_ids
    if active(state):
        selected=entry.get('default_versions',{}).get(field_id)
        if field_id in expression_ids(state,entry):
            version=next((v for v in entry.get('expression_versions',[]) if v['id']==entry.get('profile_default_set_id') and not v.get('deleted_at')),None)
            selected=(version or {}).get('field_versions',{}).get(field_id)
        return next((v for v in versions if v['id']==selected),None)
    return next((v for v in versions if v["id"] == entry.get("default_versions", {}).get(field_id)), versions[0] if versions else None)


def put_answer(state, entry, field, content, mode="new", target_id=None, name="新版本", source=None):
    from recognizer import compact
    if field.get("entry_id") and field["entry_id"]!=entry["id"]:raise LabError("字段只属于创建它的资料，不能写入其他记录")
    content = validate_value(field, content)
    store = state["versions" if field["type"] == "versioned_text" else "answer_versions"]
    versions = [v for v in all_versions(state, entry["id"], field["id"]) if not v.get('profile_deleted')]
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
    if field["type"] != "versioned_text" and current is not None:
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
        if preview.get("parser_contract"):continue
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
            decision=preview.get('identity_decisions',{}).get(group)
            values={c['field_id']:c['value'] for c in rows}
            choices=[]
            if cat in {'employment','honors'} and not all(c.get('saved') for c in rows):
                for entry in state['entries']:
                    old=entry.get('values',{})
                    if entry['category']!=cat or entry.get('profile_archived'):continue
                    if cat=='honors' and compact(values.get('award_name',''))==compact(old.get('award_name','')) and values.get('award_name') and (not values.get('award_date') or not old.get('award_date')):
                        choices.append(entry['id'])
                    if cat=='employment' and values.get('company') and values.get('role') and all(compact(values.get(k,''))==compact(old.get(k,'')) for k in ('company','role')) and (not values.get('started') or not old.get('started') or values['started']==old['started']) and values.get('ended')!=old.get('ended'):
                        choices.append(entry['id'])
            review=bool(choices) and not decision
            if decision:key='entry:'+decision['entry_id'] if decision.get('entry_id') else preview['id']+'/'+group+'/separate'
            elif review:key=preview['id']+'/'+group+'/review'
            for c in rows:
                c['identity_review']=review
                c['identity_choices']=choices
                c["identity_key"] = key
                c["import_id"] = preview["id"]
            grouped.setdefault(key, []).extend(rows)
    for key, rows in grouped.items():
        cat = rows[0]["category"]
        entries = [e for e in state["entries"] if e["category"] == cat]
        if category(cat)[2]:
            matches = [e for e in entries if (key=="entry:"+e["id"]) or (not key.startswith("entry:") and (e.get("identity_key") == key or identity_key(cat, e["values"]) == key))]
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
            if c.get("identity_review"):
                c["status"],c["selected"]="需确认归属",False
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
        if preview.get("parser_contract"):continue
        changed = signatures[preview["id"]] != [(c.get("entry_id"), c.get("existing"), c.get("status"), c.get("duplicate_of")) for c in preview["candidates"]]
        preview["revision"] = preview.get("revision", 1) + int(changed)

    from resume_import import reconcile
    reconcile(state)


def normalize_startup(state):
    """Shared deterministic startup upgrades, also used by migration rehearsal."""
    for preview in state['imports']:
        if preview.get('status') == '识别中':
            preview.update(status='已中断', stage='已中断', error='服务重启中断了识别，原文件已保留，可以重试。')
    state.setdefault("answer_versions", [])
    for key, label, repeatable in CATEGORIES:
        if not any(c['id'] == key for c in state['categories']):
            state['categories'].append({'id': key, 'label': label, 'repeatable': repeatable})
    for field in state["fields"]:
        if field["id"] in {"started", "ended", "graduation_date"} and field["type"] == "date":
            field["type"] = "partial_date"
    for entry in state["entries"]:
        for field_id, value in entry["values"].items():
            field = next((f for f in state["fields"] if f["id"] == field_id), None)
            if field and not all_versions(state, entry["id"], field_id):
                put_answer(state, entry, field, value, name="已确认版本", source=entry["sources"].get(field_id))
        for version in state["versions"]:
            if version["entry_id"] == entry["id"]:
                from profile_contract import active,expression_ids
                if active(state) and version['field_id'] in expression_ids(state,entry):continue
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
    from profile_schema import install
    install(state)
    for stored in state["categories"]:
        from profile_contract import category_for
        definition=category_for(state,stored["id"])
        if definition:stored.update(label=definition[1],repeatable=definition[2])


class Lab:
    def __init__(self, directory, recognizer=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.recognizer = recognizer
        self.import_workers = {}
        self.db = sqlite3.connect(self.directory / "lab.sqlite", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, body BLOB NOT NULL)")
        if not self.db.execute("SELECT 1 FROM state WHERE id=1").fetchone():
            self.db.execute("INSERT INTO state VALUES (1,?)", (json.dumps(initial_state(), ensure_ascii=False),))
        self.db.commit()
        self.mutate(normalize_startup)

    def state(self):
        with self.lock:
            return json.loads(self.db.execute("SELECT body FROM state WHERE id=1").fetchone()[0])

    def mutate(self, action):
        with self.lock, self.db:
            if not self.db.in_transaction:self.db.execute('BEGIN IMMEDIATE')
            state = self.state()
            from profile_contract import active
            if active(state):
                from profile_trash import expire
                expire(state)
            result = action(state)
            reconcile_semantic_imports(state)
            self.db.execute("UPDATE state SET body=? WHERE id=1", (json.dumps(state, ensure_ascii=False),))
            return copy.deepcopy(result)

    def upload(self, filename, raw, asynchronous=False):
        filename = Path(filename.replace("\\", "/")).name
        if not filename or len(filename) > 180 or not raw or len(raw) > 8 * 1024 * 1024:
            raise LabError("文件名无效或文件超过 8 MiB")
        if asynchronous:
            def create(state):
                file_id = uid('file')
                self.db.execute('INSERT INTO files VALUES (?,?)', (file_id, raw))
                state['files'].append(dict(id=file_id, name=filename, size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
                preview = dict(id=uid('import'), file_id=file_id, filename=filename, candidates=[], semantic=bool(self.recognizer), status='待识别', stage='原文件已保存', started_at=time.time(), extractor=self.recognizer.name if self.recognizer else '带标签示例解析（测试模式）')
                state['imports'].append(preview)
                return preview
            preview = self.mutate(create)
            return self.start_import(preview['id'])
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
                **conversion_metadata(blocks)}
            state["imports"].append(preview)
            return preview
        preview = self.mutate(save)
        if self.recognizer:
            return self.recognize_import(preview["id"], blocks)
        return preview

    def start_import(self, import_id):
        with self.lock:
            preview = find(self.state()['imports'], import_id)
            if any(c.get('saved') for c in preview['candidates']):
                raise LabError('已有资料已保存，请重新上传建立新预览')
            if import_id in self.import_workers and self.import_workers[import_id].is_alive():
                return preview
            self.mutate(lambda s: find(s['imports'], import_id).update(status='识别中', stage='转换为 Markdown', error='', error_code='', diagnostics={}, started_at=time.time()))
            def run():
                try:
                    meta, raw = self.file_bytes(preview['file_id'])
                    blocks = extract_text(meta['name'], raw)
                    if sum(len(b['text']) for b in blocks) > 80000:
                        raise LabError('文档正文超过本轮识别的 80000 字符限制')
                    self.mutate(lambda s: find(s['imports'], import_id).update(**conversion_metadata(blocks)))
                    if self.recognizer:
                        self.recognize_import(import_id, blocks)
                    else:
                        self.mutate(lambda s: finish_preview(s, import_id, parse_sample_fields(s, blocks, meta['name']), [], {}))
                except Exception as error:
                    self.mutate(lambda s: find(s['imports'], import_id).update(status='失败', stage='失败', error=str(error)[:1000], finished_at=time.time()))
                finally:
                    def record_attempt(state):
                        task=find(state['imports'],import_id)
                        history=task.setdefault('attempts',[])
                        history.append({key:copy.deepcopy(task.get(key)) for key in ('started_at','finished_at','status','error_code','diagnostics')})
                        task['attempts']=history[-20:]
                    self.mutate(record_attempt)
            worker = threading.Thread(target=run, daemon=True)
            self.import_workers[import_id] = worker
            worker.start()
            return find(self.state()['imports'], import_id)

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
        from document_review import clean_blocks
        if not all(b.get("cleanup_version") for b in blocks):blocks=clean_blocks(blocks)
        self.mutate(lambda s: find(s["imports"], import_id).update(status="识别中", stage="按资料组识别内容", error="", error_code='', diagnostics={}, **conversion_metadata(blocks)))
        if not any(b["text"].strip() for b in blocks):
            return self.mutate(lambda s: finish_preview(s, import_id, [], ["未读取到文字层；扫描 PDF 尚未接入 OCR，可以上传文字版或手填资料。"], {}))
        try:
            from resume_skill import rules, catalog, compare
            from resume_import import comparison_token
            current=self.state(); _, digest=rules()
            adapter=hashlib.sha256((Path(__file__).with_name('recognizer.py').read_bytes()+Path(__file__).with_name('resume_skill.py').read_bytes()+Path(__file__).with_name('document_review.py').read_bytes())).hexdigest()
            cache_key=comparison_token({'blocks':blocks,'fields':catalog(current['fields']),'skill':digest,'adapter':adapter})
            cached=next((p for p in reversed(current['imports']) if p.get('extraction_cache_key')==cache_key and p.get('model_result',{}).get('parser_contract')),None)
            if cached:
                result,usage=copy.deepcopy(cached.get('extraction_result',cached['model_result'])),{**cached.get('usage',{}),'extraction_cached':True}
            else:
                result, usage = self.recognizer.extract(current["fields"], blocks)
            self.mutate(lambda s: find(s['imports'],import_id).update(extraction_cache_key=cache_key))
            # Keep the model draft only in this temporary application session so
            # deterministic validation can be repaired without resending a resume.
            self.mutate(lambda s: find(s['imports'],import_id).update(extraction_result=copy.deepcopy(result)))
            from document_review import needs_source,review_source
            source_warnings=[]
            if result.get('parser_contract') and needs_source(result):
                self.mutate(lambda s: find(s['imports'],import_id).update(stage='结合原PDF/Word核对版式与归属'))
                meta,raw=self.file_bytes(preview['file_id'])
                try:
                    blocks,result,source_review=review_source(self.recognizer,current['fields'],blocks,result,meta['name'],raw)
                except RecognitionError as error:
                    source_review={'failed':True,'reason':'原件模型核对未完成，保留原提取结果和疑点','code':error.code}
                if source_review.get('failed'):source_warnings.append(source_review['reason'])
                self.mutate(lambda s:find(s['imports'],import_id).update(source_review=source_review,**conversion_metadata(blocks)))
                usage={**usage,'source_review':source_review}
            self.mutate(lambda s: find(s['imports'], import_id).update(model_result=result, stage='核验来源与整理资料组'))
            candidates, rejected = grounded_candidates(self.state(), blocks, preview["filename"], result)
            additional_warnings=list(source_warnings)
            if result.get('parser_contract') and rejected:
                from resume_skill import repair
                self.mutate(lambda s: find(s['imports'],import_id).update(stage='局部核对未通过的原文引用',model_result_before_repair=result))
                try:
                    result,repair_info=repair(self.recognizer,self.state()['fields'],blocks,result,candidates)
                except RecognitionError as error:
                    repair_info={'failed':True,'code':error.code,'diagnostics':error.diagnostics}
                    additional_warnings.append('局部模型核对未完成；原提取结果保留，未通过核验的资料组暂不能保存。')
                candidates,rejected=grounded_candidates(self.state(),blocks,preview['filename'],result)
                self.mutate(lambda s: find(s['imports'],import_id).update(model_result=result,repair_info=repair_info))
                usage={**usage,'repair':repair_info}
            if result.get('parser_contract'):
                self.mutate(lambda s: find(s['imports'],import_id).update(stage='比较已有资料与表述版本'))
                comparison_failed=False
                try:
                    hints,comparison_usage=compare(self.recognizer,self.state(),candidates,import_id)
                except RecognitionError as error:
                    hints={};comparison_usage={'failed':True,'code':error.code,'diagnostics':error.diagnostics};comparison_failed=True
                    additional_warnings.append('语义比较未完成；已有确定相同项可复用，其余与现有资料的归属须确认。')
                self.mutate(lambda s: find(s['imports'],import_id).update(comparison_hints=hints,comparison_failed=comparison_failed))
                usage={**usage,'parser_contract':result['parser_contract'],'comparison_usage':comparison_usage}
            warnings = [str(w) for w in result.get("warnings", [])] + rejected + additional_warnings
            self.mutate(lambda s: finish_preview(s, import_id, candidates, warnings, usage))
            return find(self.state()["imports"], import_id)
        except RecognitionError as error:
            self.mutate(lambda s: find(s["imports"], import_id).update(status="失败", error=str(error), error_code=error.code, diagnostics=error.diagnostics))
            raise LabError(str(error), 502)

    def revalidate_import(self, import_id):
        from recognizer import grounded_candidates, RecognitionError
        preview = find(self.state()["imports"], import_id)
        if any(c["saved"] for c in preview["candidates"]):
            raise LabError("已有资料已保存，不能替换此预览")
        if not preview.get("model_result"):
            raise LabError("此旧预览没有模型草稿，请重新识别")
        blocks = preview.get('document_blocks')
        if not blocks:
            raise LabError('旧预览没有保存 Markdown 来源，请重新识别后核验，已保存资料不受影响')
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
            # Confirmed historical imports keep their existing contract; new Skill
            # imports are saved as whole representations in the same transaction.
            tagged={c['id'] for p in state['imports'] if p.get('parser_contract') for c in p['candidates']}
            if state.get('profile_contract')==30:
                legacy={c['id'] for p in state['imports'] if not p.get('parser_contract') for c in p['candidates'] if candidate_pending(c)}
                if any(d.get('candidate_id') in legacy and d.get('mode')!='ignore' for d in decisions):
                    raise LabError('此候选来自旧解析契约，已保留原件与旧结果；请明确重新解析后再按新版规则核对保存',409)
            if len({d['candidate_id'] for d in decisions})!=len(decisions):raise LabError('同一增量不能重复处理')
            for pid, revision in (revisions or {}).items():
                if revision != find(state["imports"], pid).get("revision", 1):
                    raise LabError("资料已更新，请重新打开增量预览", 409)
            if any(d['candidate_id'] in tagged for d in decisions):
                if not all(d['candidate_id'] in tagged for d in decisions):raise LabError('请分别处理新旧解析任务')
                affected={p['id']:p for p in state['imports'] if any(c['id'] in {d['candidate_id'] for d in decisions if d['mode']!='ignore'} for c in p['candidates'])}
                if any(p.get('review_contract') and not p.get('review_completed') for p in affected.values()):raise LabError('请先完成确认表单；缺项可全部跳过',409)
                from resume_import import resolve
                return resolve(self,state,decisions)
            rows = {c["id"]: (p, c) for p in state["imports"] for c in p["candidates"]}
            groups, saved, ignored = {}, 0, 0
            requested = {d['candidate_id']: d for d in decisions}
            pending_sets = {}
            for pid, candidate in rows.values():
                if category(candidate['category'])[2] and candidate_pending(candidate):
                    pending_sets.setdefault((pid['id'], candidate['group']), []).append(candidate['id'])
            for ids in pending_sets.values():
                chosen = [cid for cid in ids if cid in requested]
                if chosen and (len(chosen) != len(ids) or len({requested[cid]['mode'] for cid in chosen}) != 1):
                    raise LabError('请按完整资料组处理：同一段经历或同一项资料的待处理字段须一起保存或忽略', 409)
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
                if candidate.get("identity_review"):
                    raise LabError("请先确认这一组是已有经历/获奖，还是独立资料",409)
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
        from profile_contract import category_for,active
        if not category(cat):
            raise LabError("未知资料分类")
        if active(state) and cat in {'preferences','social'}:raise LabError('此类别已取消，不再创建预设对象')
        existing = [e for e in state["entries"] if e["category"] == cat and not e.get("profile_archived") and not e.get('legacy_only')]
        if existing and not category_for(state,cat)[2]:
            return existing[0]
        entry = {"id": uid(cat), "category": cat, "values": {}, "sources": {}, "default_versions": {}}
        state["entries"].append(entry)
        return entry

    def add_field(self, request):
        def add(state):
            if state.get('profile_contract') == 30:
                from profile_current import add_custom_field
                return add_custom_field(state, request)
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
            if state.get('profile_contract') == 30:
                raise LabError('请通过当前资料保存入口核对修改与编辑标识', 409)
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
            if state.get('profile_contract') == 30:
                raise LabError('不再提供字段版本；请编辑任职或项目的表达版本', 409)
            field = find(state["fields"], field_id)
            entry = find(state["entries"], entry_id)
            if field["category"] != entry["category"]:
                raise LabError("版本不属于该字段或资料条目")
            return put_answer(state, entry, field, content, name=name)
        return self.mutate(create)

    def set_default(self, entry_id, field_id, version_id):
        def update(state):
            if state.get('profile_contract') == 30:
                raise LabError('请通过表达版本设置默认；普通字段只有当前值', 409)
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
            if state.get('profile_contract') == 30:
                raise LabError('请通过本次投递材料编辑入口保存', 409)
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
            if state.get('profile_contract') == 30:
                raise LabError('请通过本次投递材料编辑入口保存', 409)
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
            if state.get('profile_contract') == 30:
                raise LabError('请选择完整表达版本，不再单独切换字段版本', 409)
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
            from profile_schema import available
            entries = [e for e in state["entries"] if e["category"] == cat["id"] and available(e,session)]
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
