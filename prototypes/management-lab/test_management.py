"""Disposable fictional data; no live Feishu writes or profile-lab access."""
import json
import tempfile
import unittest
import uuid
from unittest.mock import patch
import feishu
from store import Store, Invalid, Conflict, Missing


def sample(role="测试岗位", stage="已投递", kind="applications"):
    return feishu.candidate({"kind": kind, "name": "测试表"}, {"record_id": "fictional-record", "fields": {
        "公司名称": "虚构公司", "公司": "虚构公司", "岗位名称": role, "投递链接": "https://example.com/job", "面试进度": stage,
        "投递状态": "高优投递", "投递时间线": "原文日期参考", "面试记录及复盘": "合并原文", "自建列": "保留值"}})


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="management-test-")
        self.store = Store(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def add(self, c=None, key=None):
        c = c or sample()
        return self.store.import_selected([c], [{"id": c["id"]}], key or str(uuid.uuid4()), {"selected": c["id"]})["ids"][0]

    def test_status_does_not_become_stage_or_dates(self):
        c=sample(); self.assertEqual(c["recruitment_stage"], "")
        j=self.store.get(self.add(c)); self.assertEqual(j["application_status"], "已投递"); self.assertEqual(j["timeline"], [])
        self.assertEqual(j["legacy_fields"]["自建列"], "保留值"); self.assertEqual(j["interview_notes"], "")

    def test_opportunity_priority_never_becomes_recruitment_stage(self):
        c=sample(stage="", kind="opportunities")
        self.assertEqual(c["application_status"], "未投递"); self.assertEqual(c["recruitment_stage"], "")
        self.assertEqual(c["legacy_status"], "高优投递")

    def test_same_business_normal_new_and_one_request_idempotent(self):
        c=sample(); key=str(uuid.uuid4()); j=self.add(c,key)
        self.assertEqual(self.add(c,key), j); other=self.add(c); self.assertNotEqual(other,j); self.assertEqual(len(self.store.list_jobs()),2)
        self.store.delete(j,1,True); self.assertEqual(self.add(c,key),j); self.assertEqual(len(self.store.list_jobs()),1)

    def test_missing_role_and_multi_role_need_user_decision(self):
        for role in ("", "测试岗位甲、测试岗位乙"):
            c=sample(role); self.assertEqual(c["role"], "")
            with self.assertRaises(Invalid): self.add(c)
        self.assertEqual(sample("岗位甲、岗位乙", "二面")["recruitment_stage"], "")

    def test_custom_stage_and_manual_confirmation_independent(self):
        j=self.store.get(self.add(sample(stage="",kind="opportunities")))
        j=self.store.update(j["id"],j["revision"],{"application_status":"已投递"},None)
        self.assertEqual(j["recruitment_stage"],""); self.assertEqual(j["timeline"],[])
        j=self.store.update(j["id"],j["revision"],{"recruitment_stage":"四面待结果"},None)
        self.assertEqual(j["recruitment_stage"],"四面待结果"); self.assertEqual(j["timeline"],[])

    def test_appointment_and_interview_dates_are_distinct(self):
        j=self.store.get(self.add()); dates=[{"label":"约一面日期","day":"2026-10-01"},{"label":"一面日期","day":"2026-10-03"}]
        j=self.store.update(j["id"],j["revision"],{},dates)
        self.assertEqual(len(j["timeline"]),2); self.assertEqual(j["recruitment_stage"],"")

    def test_invalid_date_is_atomic_and_does_not_save_other_edits(self):
        j=self.store.get(self.add())
        with self.assertRaises(Invalid): self.store.update(j["id"],1,{"recruitment_stage":"Offer"},[{"label":"一面日期","day":"2026-02-30"}])
        self.assertEqual(self.store.get(j["id"])["recruitment_stage"], "")

    def test_revision_conflicts_preserve_later_edit(self):
        j=self.add(); self.store.update(j,1,{"recruitment_stage":"测评"},None)
        with self.assertRaises(Conflict): self.store.update(j,1,{"recruitment_stage":"Offer"},None)
        with self.assertRaises(Conflict): self.store.delete(j,1,True)
        self.assertEqual(self.store.get(j)["recruitment_stage"],"测评")

    def test_delete_cascades_but_keeps_other_job_and_no_late_recreate(self):
        j=self.add(); other=self.add()
        self.store.update(j,1,{"interview_notes":"虚构笔记","review_notes":"虚构复盘"},[{"label":"投递日期","day":"2026-10-10"}])
        with self.store.connect() as db: db.execute("INSERT INTO executions VALUES ('fictional-exec',?,?)", (j,'{}'))
        with self.assertRaises(Invalid): self.store.delete(j,2,False)
        self.store.delete(j,2,True)
        with self.assertRaises(Missing): self.store.update(j,2,{"recruitment_stage":"Offer"},None)
        self.assertEqual(self.store.get(other)["id"],other)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM dates").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM executions").fetchone()[0],0)

    def test_preview_has_no_automatic_import_or_dates(self):
        p=self.store.preview_text("公司 | 岗位 | 投递链接\n虚构公司 | 岗位甲 | https://example.com/a\n虚构公司 | 岗位乙 | https://example.com/b")
        self.assertEqual(len(p["candidates"]),2); self.assertEqual(self.store.list_jobs(),[])
        self.add(p["candidates"][1]); self.assertEqual(len(self.store.list_jobs()),1)
        self.assertEqual(self.store.list_jobs()[0]["application_status"],"未投递")

    def test_source_text_and_unmapped_fields_preserved(self):
        p=self.store.preview_text("只有原文，尚未明确公司和岗位")
        self.assertEqual(p["candidates"][0]["source_text"],"只有原文，尚未明确公司和岗位")
        with self.assertRaises(Invalid): self.add(p["candidates"][0])

    def test_unsafe_urls_and_unknown_fields_rejected(self):
        c=sample(); c["url"]="javascript:alert(1)"
        with self.assertRaises(Invalid): self.add(c)
        j=self.add()
        with self.assertRaises(Invalid): self.store.update(j,1,{"remote_write_enabled":True},None)

    def test_adapter_writes_rejected_before_subprocess(self):
        with patch("feishu.subprocess.run") as run:
            for args in (["base","+record-batch-update"],["base","+field-create"],["base","+record-delete"],["drive","permission.members","create"]):
                with self.assertRaises(feishu.FeishuError): feishu.cli(args)
            run.assert_not_called()


if __name__ == '__main__': unittest.main(verbosity=2)
