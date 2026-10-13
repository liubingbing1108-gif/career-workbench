"""Read-only Feishu adapter. No mutation commands belong in this module."""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
from pathlib import Path
import subprocess
from datetime import datetime, timezone

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config/feishu.local.json"
READ_COMMANDS = {"+base-get", "+table-list", "+field-list", "+record-list", "+workflow-list"}


class FeishuError(Exception):
    pass


def cli(args):
    allowed = (args[:2] == ["base", args[1]] and args[1] in READ_COMMANDS) or args[:2] in [
        ["auth", "status"], ["drive", "permission.members"],
    ]
    if not allowed or (args[:2] == ["drive", "permission.members"] and args[2] != "auth"):
        raise FeishuError("飞书适配器只允许读取")
    env = {**os.environ, "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1", "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1"}
    try:
        result = subprocess.run(["lark-cli", *args], capture_output=True, text=True, timeout=60, env=env)
        data = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise FeishuError("飞书读取未完成，请检查 CLI 登录或网络后重试") from exc
    if result.returncode or data.get("ok") is False:
        raise FeishuError("飞书读取失败；保留上次预览，请检查 CLI 登录、网络与表权限")
    return data.get("data", data)


def paged(command, base, table=None, fields=()):
    rows, offset = [], 0
    while True:
        args = ["base", command, "--base-token", base, "--as", "user", "--format", "json", "--limit", "200" if table else "100", "--offset", str(offset)]
        if table:
            args += ["--table-id", table]
        for name in fields:
            args += ["--field-id", name]
        data = cli(args)
        if command == "+record-list":
            ids, values = data.get("record_id_list", []), data.get("data", [])
            if len(ids) != len(values):
                raise FeishuError("飞书返回的记录与 ID 数量不一致，未覆盖缓存")
            page = [{"record_id": rid, "fields": dict(zip(data["fields"], vals))} for rid, vals in zip(ids, values)]
        else:
            page = data.get("fields" if table else "tables", [])
        rows.extend(page)
        if not data.get("has_more") and len(rows) >= data.get("total", len(rows)):
            return rows
        if not page:
            raise FeishuError("飞书分页不完整，未覆盖缓存")
        offset += len(page)


def fetch_snapshot(config=DEFAULT_CONFIG):
    cfg = json.loads(Path(config).read_text())["destination"]
    base, ids = cfg["base_token"], cfg["tables"]
    info = cli(["base", "+base-get", "--base-token", base, "--as", "user"])["base"]
    tables = paged("+table-list", base)
    permission = cli(["drive", "permission.members", "auth", "--token", base, "--type", "bitable", "--action", "edit", "--as", "user"])
    workflows = cli(["base", "+workflow-list", "--base-token", base, "--as", "user"])
    snapshot = {"fetched_at": datetime.now(timezone.utc).isoformat(), "base": {k: info.get(k) for k in ("name", "url", "is_advanced")},
                "permissions": {"read_verified": True, "edit_verified": permission.get("auth_result") is True, "remote_write_enabled": False},
                "workflows": [{k: w.get(k) for k in ("title", "status", "workflow_id")} for w in workflows.get("items", [])], "tables": []}
    for kind in ("applications", "opportunities"):
        tid = ids[kind]
        table = next((t for t in tables if t["id"] == tid), None)
        if not table:
            raise FeishuError("配置中的目标表未找到，未覆盖缓存")
        fields = paged("+field-list", base, tid)
        records = paged("+record-list", base, tid, [f["name"] for f in fields])
        snapshot["tables"].append({"kind": kind, "id": tid, "name": table["name"], "fields": fields, "records": records,
                                   "count": len(records), "listed_count": table.get("records_count")})
    return snapshot


def save_snapshot(snapshot, data_dir):
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = folder / "feishu-snapshot.pending"
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(folder / "feishu-snapshot.json")


def cell(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "、".join(cell(v) for v in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("url") or json.dumps(value, ensure_ascii=False))
    return str(value)


def outcome(fields):
    """Only a whole, explicit result is a stage; free-form interview notes stay notes."""
    value = cell(fields.get('面试记录及复盘')).strip()
    return value if re.fullmatch(r'(?:简历挂|用人部门简历挂|笔试挂|测评挂|面试挂|[一二三四五六七八九十终]面挂|群面挂|群面/一面挂)', value) else ''


def candidate(table, row):
    f, history = row["fields"], table["kind"] == "applications"
    legacy_stage = cell(f.get("面试进度"))
    legacy_status = cell(f.get("投递状态"))
    applied = history or legacy_status == "已投递"
    # “已投递” is an application fact, never a recruitment stage.
    stage = legacy_stage if legacy_stage != "已投递" else ""
    notes = ["志愿顺序：原表缺少字段", "日期时间线：仅保留原文供人工记录", "面试记录／复盘：原表合并字段，尚未拆分"]
    if not history:
        notes += ["原投递状态含优先级语义，不作为新招聘进度"]
    if legacy_stage == "已投递":
        notes += ["原面试进度“已投递”不映射为招聘进度"]
    company, role = cell(f.get("公司名称" if history else "公司")), cell(f.get("岗位名称"))
    role_summary = bool(re.search(r"[、；;]|\n", role))
    legacy_role = role
    if role_summary:
        role, stage = "", ""
        notes += ["原行合写多个岗位：需拆分或补齐具体岗位；旧汇总招聘进度不自动分配"]
    if not role:
        notes += ["缺少具体岗位名称：请补齐后选择导入；不按公司拆造岗位"]
    result = outcome(f) if history else ''
    if result:
        stage = result
        notes += ['原合并备注中的明确招聘结果归入招聘进度；合写行不传播到拆分岗位']
    return {"id": table["kind"] + ":" + row["record_id"], "company": company, "role": role,
            "url": cell(f.get("投递链接")), "application_status": "已投递" if applied else "未投递", "recruitment_stage": stage,
            "preference_order": "", "requires_preference": False,
            "location": cell(f.get("工作地点")), "campaign": cell(f.get("招聘批次")),
            "historical_applied": applied, "source_table": table["name"], "source_record_id": row["record_id"],
            "legacy_role": legacy_role, "role_summary": role_summary,
            "legacy_status": legacy_stage if history else legacy_status, "legacy_fields": f, "mapping_notes": notes,
            "source_kind": "feishu", "source_text": "", "source_url": cell(f.get('投递链接')),
            "official_url_status": "unverified", "outcome_from_legacy_notes": bool(result)}


def candidates(snapshot):
    return [candidate(table, row) for table in snapshot.get("tables", []) for row in table["records"]]


def summary(snapshot):
    return {"base": snapshot["base"]["name"], "permissions": snapshot["permissions"], "tables": [
        {"kind": t["kind"], "count": t["count"], "fields": len(t["fields"]),
         "missing_role": sum(not cell(r["fields"].get("岗位名称")) for r in t["records"]),
         "multi_role": sum(bool(re.search(r"[、；;]|\n", cell(r["fields"].get("岗位名称")))) for r in t["records"]),
         "legacy_stages": dict(collections.Counter(cell(r["fields"].get("面试进度" if t["kind"] == "applications" else "投递状态")) for r in t["records"]))} for t in snapshot["tables"]],
        "enabled_workflows": sum(w["status"] == "enabled" for w in snapshot["workflows"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    snapshot = fetch_snapshot(args.config)
    save_snapshot(snapshot, args.data_dir)
    print(json.dumps(summary(snapshot), ensure_ascii=False, indent=2))
