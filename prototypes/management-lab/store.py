from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
import sqlite3
import uuid
from datetime import date
from urllib.parse import urlsplit

STAGES = ["待筛选", "笔试", "测评", "一面", "二面", "三面", "终面", "待结果", "Offer", "未通过", "流程结束", "主动放弃"]
EDITABLE = {"company", "role", "url", "source_url", "official_url", "preference_order", "requires_preference", "application_status", "recruitment_stage", "location", "campaign", "interview_notes", "review_notes", "timeline_text"}


class Invalid(Exception):
    pass


class Conflict(Exception):
    pass


class Missing(Exception):
    pass


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def safe_url(value):
    value = str(value or "").strip()
    if value and (urlsplit(value).scheme not in ("https", "http") or not urlsplit(value).hostname):
        raise Invalid("来源链接请使用完整的 http／https 地址")
    return value


def link_fields(job):
    """Project old records without treating an unverified source as a destination."""
    source = job.get('source_url')
    if source is None or ('official_url' not in job and not source):source=job.get('url','')
    official = job.get('official_url')
    if official is None:
        official = (job.get('official_entry', {}).get('url') or job.get('url', '')) if job.get('official_url_status') == 'verified' else ''
    return {**job, 'source_url': source, 'official_url': official}


def validate_job(job):
    for key in EDITABLE - {"requires_preference"}:
        if not isinstance(job.get(key, ""), str) or len(job.get(key, "")) > 20000:
            raise Invalid("字段内容或长度无效")
    incomplete = not job.get("company", "").strip() or not job.get("role", "").strip()
    if incomplete and job.get('needs_review') is not True:
        raise Invalid("请补齐公司和具体岗位名称；公司汇总不能代替岗位记录")
    multi_role = bool(job.get("role_summary") and re.search(r"[、；;]|\n", job.get('role', '')))
    if multi_role and job.get('needs_review') is not True:
        raise Invalid("原行包含多个岗位，请使用拆分预览或填写其中一个具体岗位")
    if not isinstance(job.get("requires_preference", False), bool):
        raise Invalid("志愿提示值无效")
    if job.get("application_status") not in ("未投递", "已投递"):
        raise Invalid("投递状态仅支持未投递／已投递")
    safe_url(job.get("url"))
    job.update(link_fields(job))
    job['source_url'] = safe_url(job['source_url'])
    job['official_url'] = safe_url(job['official_url'])
    if job['official_url'] and urlsplit(job['official_url']).scheme != 'https':
        raise Invalid('官网投递链接请使用完整的HTTPS地址')
    job['url'] = job['source_url']  # Legacy intake alias; never an execution destination.
    job["company"], job["role"] = job["company"].strip(), job["role"].strip()
    if 'needs_review' in job: job['needs_review'] = incomplete or multi_role
    if len(job.get("recruitment_stage", "")) > 100:
        raise Invalid("招聘进度最多 100 字")
    return job


def text_candidates(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 100000:
        raise Invalid("请输入招聘文本，最多 10 万字")
    lines = [line for line in text.splitlines() if line.strip()]
    separator = "\t" if "\t" in text else "|"
    parsed = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=separator))
    if parsed and parsed[0][0].strip() in ("公司", "公司名称"):
        parsed.pop(0)
    out = []
    for i, parts in enumerate(parsed):
        parts = [p.strip() for p in parts]
        structured = len(parts) >= 2
        out.append({"id": str(i), "company": parts[0] if structured else "", "role": parts[1] if structured else "",
                    "url": parts[2] if len(parts) > 2 else (parts[0] if parts[0].startswith(("http://", "https://")) else ""),
                    "application_status": "未投递", "recruitment_stage": "", "preference_order": "", "requires_preference": False,
                    "location": "", "campaign": "", "source_kind": "text", "source_table": "人工输入", "source_record_id": "",
                    "source_text": lines[i + (len(lines) - len(parsed))], "source_url": "", "legacy_fields": {}, "legacy_status": "",
                    "mapping_notes": [] if structured else ["未连接网页／自然语言解析，请依据原文补齐公司及岗位后选择"], "historical_applied": False})
    return out


class Store:
    def __init__(self, data_dir):
        self.folder = Path(data_dir)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.folder / "management.sqlite3"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS dates(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, label TEXT NOT NULL, day TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS executions(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, job_ids TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS migrations(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, factory=ManagedConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _get(self, db, job_id):
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise Missing("该岗位已删除或不存在；旧结果不会重建记录")
        data = link_fields(json.loads(row["payload"]))
        data.update(id=row["id"], revision=row["revision"])
        data["timeline"] = [dict(r) for r in db.execute("SELECT id,label,day FROM dates WHERE job_id=? ORDER BY day,label,id", (job_id,))]
        data["execution_count"] = db.execute("SELECT count(*) FROM executions WHERE job_id=?", (job_id,)).fetchone()[0]
        return data

    def list_jobs(self):
        with self.connect() as db:
            return [self._get(db, r[0]) for r in db.execute("SELECT id FROM jobs ORDER BY rowid DESC").fetchall()]

    def get(self, job_id):
        with self.connect() as db:
            return self._get(db, job_id)

    def preview_text(self, text):
        rows = text_candidates(text)
        return self.save_preview(rows)

    def create_link(self, url, request_id):
        url = safe_url(url)
        if not url: raise Invalid('请填写招聘申请链接')
        job = {'id': 'link', 'company': '', 'role': '', 'url': url, 'needs_review': True,
               'source_url': url, 'official_url_status': 'unverified',
               'application_status': '未投递', 'recruitment_stage': '', 'preference_order': '',
               'requires_preference': False, 'source_kind': 'workbench', 'source_table': '投递工作台',
               'source_text': url, 'mapping_notes': ['公司与岗位将在读取官网后补充；不猜测岗位身份']}
        result = self.import_selected([job], [{'id':'link'}], request_id, {'url':url,'from':'workbench'})
        return self.get(result['ids'][0])

    def save_preview(self, rows):
        pid = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO previews VALUES (?,?)", (pid, json.dumps(rows, ensure_ascii=False)))
        return {"batch_id": pid, "candidates": rows}

    def preview(self, pid):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM previews WHERE id=?", (pid,)).fetchone()
        if not row:
            raise Missing("预览已不存在，请重新生成")
        return json.loads(row[0])

    def import_selected(self, all_candidates, selections, request_id, request_body):
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
            raise Invalid("入库请求标识无效")
        if not isinstance(selections, list) or not 1 <= len(selections) <= 500:
            raise Invalid("请先选择候选岗位")
        fingerprint = hashlib.sha256(json.dumps(request_body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        by_id = {c["id"]: c for c in all_candidates}
        prepared = []
        for sel in selections:
            if sel.get("id") not in by_id:
                raise Invalid("所选候选不在本次预览范围内")
            original = by_id[sel["id"]]
            patch = sel.get("patch", {})
            if set(patch) - EDITABLE:
                raise Invalid("候选编辑包含未知字段")
            job = {**link_fields(original), **patch, "interview_notes": patch.get("interview_notes", ""), "review_notes": patch.get("review_notes", "")}
            if 'url' in patch and 'source_url' not in patch:job['source_url']=patch['url']
            job.setdefault('source_url', original.get('url', ''))
            job.setdefault('official_url_status','unverified')
            job.pop("id", None)
            prepared.append(validate_job(job))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            receipt = db.execute("SELECT * FROM receipts WHERE id=?", (request_id,)).fetchone()
            if receipt:
                if receipt["request_hash"] != fingerprint:
                    raise Conflict("相同请求标识不能用于不同选择")
                # Receipt contains only IDs. Deleted jobs never reappear on retries.
                return {"ids": json.loads(receipt["job_ids"]), "replayed": True}
            ids = []
            for job in prepared:
                jid = str(uuid.uuid4())
                db.execute("INSERT INTO jobs VALUES (?,1,?)", (jid, json.dumps(job, ensure_ascii=False)))
                ids.append(jid)
            db.execute("INSERT INTO receipts VALUES (?,?,?)", (request_id, fingerprint, json.dumps(ids)))
            return {"ids": ids, "replayed": False}

    def update(self, job_id, revision, patch, timeline):
        if not isinstance(patch, dict) or set(patch) - EDITABLE:
            raise Invalid("编辑包含未知字段")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._get(db, job_id)
            if job["revision"] != revision:
                raise Conflict("记录已在别处修改，请重新打开后编辑；当前草稿未覆盖")
            before = dict(job)
            patch = dict(patch)
            if 'url' in patch and 'source_url' not in patch:patch['source_url']=patch['url']
            job.update(patch)
            changed = any(job.get(k, '') != before.get(k, '') for k in ('company','role','location','campaign','source_url','official_url'))
            if changed:
                job['official_url_status'] = 'unverified'
                job.pop('official_entry', None)
                if job.get('official_url') == before.get('official_url'):job['official_url']=''
                job.pop('source_analysis', None)
            validate_job(job)
            if timeline is not None:
                if not isinstance(timeline, list) or len(timeline) > 200:
                    raise Invalid("日期条目无效")
                for item in timeline:
                    label, day = item.get("label", "").strip(), item.get("day", "")
                    if not label or len(label) > 100:
                        raise Invalid("请填写日期节点名称")
                    try:
                        if date.fromisoformat(day).isoformat() != day:
                            raise ValueError()
                    except (ValueError, TypeError):
                        raise Invalid("请填写有效的实际日期")
                db.execute("DELETE FROM dates WHERE job_id=?", (job_id,))
                for item in timeline:
                    db.execute("INSERT INTO dates VALUES (?,?,?,?)", (str(uuid.uuid4()), job_id, item["label"].strip(), item["day"]))
            payload = {k: v for k, v in job.items() if k not in ("id", "revision", "timeline", "execution_count")}
            db.execute("UPDATE jobs SET revision=revision+1,payload=? WHERE id=?", (json.dumps(payload, ensure_ascii=False), job_id))
            return self._get(db, job_id)

    def set_official(self, job_id, revision, entry):
        """Same-origin, revision-guarded entry from a public lookup or visible browser proof."""
        from official import validate_entry
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._get(db, job_id)
            if job['revision'] != revision:raise Conflict('记录已修改，请重新查找官网入口')
            validate_entry(job, entry)
            job.setdefault('source_url', job.get('url', ''))
            job.update(official_url=entry['url'], official_url_status='verified', official_entry=entry)
            payload = {k:v for k,v in job.items() if k not in ('id','revision','timeline','execution_count')}
            db.execute('UPDATE jobs SET revision=revision+1,payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),job_id))
            return self._get(db,job_id)

    def delete(self, job_id, revision, confirmed, related_delete=None):
        if confirmed is not True:
            raise Invalid("请先查看并确认永久删除的对象与范围")
        db = self.connect()
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                job = self._get(db, job_id)
                if job["revision"] != revision:
                    raise Conflict("岗位已变化，请重新查看删除范围后确认")
                related = related_delete(db) if related_delete else {}
                db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            return {"deleted": job_id, "remote_deleted": False, **related}
        finally:
            db.close()
