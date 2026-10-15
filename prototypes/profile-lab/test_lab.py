import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from lab import Lab, LabError
from server import make_server

SAMPLES = Path(__file__).resolve().parent / "web" / "samples"


class ProfileLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lab = Lab(self.temp.name)

    def tearDown(self):
        self.lab.db.close()
        self.temp.cleanup()

    def import_sample(self, extension="docx"):
        preview = self.lab.upload("sample." + extension, (SAMPLES / ("sample." + extension)).read_bytes())
        selected = [c["id"] for c in preview["candidates"] if c["selected"]]
        self.lab.commit_import(preview["id"], selected, {})
        return preview

    def test_blank_form_exists_without_resume_and_manual_values_work(self):
        state = self.lab.state()
        self.assertEqual(len(state["profile_modules"]), 14)
        self.assertGreater(len(state["fields"]), 200)
        self.assertFalse(state["files"])
        entry = next(e for e in state["entries"] if e["category"] == "basic")
        self.assertFalse(entry["values"])
        self.lab.save_profile([{"entry_id": entry["id"], "field_id": "name", "value": "Manual Example"}])
        self.assertEqual(self.lab.materials(self.lab.new_session()["id"])["values"]["name"], "Manual Example")

    def test_actual_pdf_docx_text_maps_to_fields_only_after_selection(self):
        for ext in ["pdf", "docx", "txt"]:
            with self.subTest(extension=ext):
                preview = self.lab.upload("sample." + ext, (SAMPLES / ("sample." + ext)).read_bytes())
                candidates = {c["field_id"]: c for c in preview["candidates"]}
                self.assertEqual(len(candidates), 13)
                self.assertEqual(candidates["email"]["value"], "sample@example.invalid")
                self.assertIn("Email" if ext != "docx" else "邮箱", candidates["email"]["source"]["quote"])
        self.assertFalse(self.lab.state()["versions"])
        self.assertFalse(next(e for e in self.lab.state()["entries"] if e["category"] == "basic")["values"])
        increments = self.lab.increments()
        self.lab.resolve_import([{"candidate_id":c["id"],"mode":"new"} for c in increments["candidates"]], increments["revisions"])
        result = self.lab.materials(self.lab.new_session()["id"])
        self.assertEqual(result["values"]["name"], "Alex Example")
        self.assertEqual(result["values"]["school"], "Example University")

    def test_original_file_bytes_survive_description_changes(self):
        preview = self.import_sample()
        original = (SAMPLES / "sample.docx").read_bytes()
        version = self.lab.state()["versions"][0]
        session = self.lab.new_session()["id"]
        self.lab.edit_version(session, version["id"], "update", "Changed description", 1)
        self.assertEqual(self.lab.file_bytes(preview["file_id"])[1], original)

    def test_conflicts_can_be_deferred_while_clear_fields_save(self):
        self.import_sample()
        self.lab.add_field({"id":"city","label":"现居城市","category":"contact","type":"text"})
        preview = self.lab.upload("changes.txt", b"Name: Other Example\nPhone: 11111111111\n" + "现居城市：示例城市".encode())
        selected = [c["id"] for c in preview["candidates"] if c["selected"]]
        result = self.lab.commit_import(preview["id"], selected, {})
        self.assertEqual(result, {"saved":1,"pending":2})
        entry = next(e for e in self.lab.state()["entries"] if e["category"] == "basic")
        self.assertEqual(entry["values"]["name"], "Alex Example")
        materials = self.lab.materials(self.lab.new_session()["id"])
        self.assertEqual(materials["values"]["name"], "Alex Example")
        self.assertEqual(materials["values"]["city"], "示例城市")

    def test_partial_repeated_entry_rejected_then_complete_set_saved_once(self):
        preview = self.lab.upload("sample.txt", (SAMPLES / "sample.txt").read_bytes())
        employment = [c["id"] for c in preview["candidates"] if c["category"]=="employment"]
        before=self.lab.state()
        with self.assertRaisesRegex(LabError,'完整资料组'):
            self.lab.commit_import(preview["id"], employment[:2], {})
        self.assertEqual(self.lab.state(),before)
        self.lab.commit_import(preview["id"], employment, {})
        self.assertEqual(len([e for e in self.lab.state()["entries"] if e["category"]=="employment"]), 1)
        self.assertEqual(len(self.lab.state()["versions"]), 1)

    def test_dynamic_field_definition_and_temporary_answer_have_separate_scope(self):
        self.lab.add_field({"id":"availability_date","label":"可到岗日期","category":"additional","type":"date"})
        a, b = self.lab.new_session()["id"], self.lab.new_session()["id"]
        self.lab.answer(a, "availability_date", "2027-07-01")
        self.assertEqual(self.lab.materials(a)["values"]["availability_date"], "2027-07-01")
        self.assertEqual(self.lab.materials(b)["values"]["availability_date"], "")
        self.lab.db.close()
        self.lab = Lab(self.temp.name)
        self.assertEqual(self.lab.materials(a)["values"]["availability_date"], "2027-07-01")
        self.assertEqual(self.lab.materials(b)["values"]["availability_date"], "")
        self.assertTrue(any(f["id"]=="availability_date" for f in self.lab.state()["fields"]))

    def test_explicit_save_to_profile_reuses_answer_in_later_session(self):
        self.lab.add_field({"id":"availability_date","label":"可到岗日期","category":"additional","type":"date"})
        a = self.lab.new_session()["id"]
        self.lab.answer(a, "availability_date", "2027-07-01", True)
        self.assertEqual(self.lab.materials(self.lab.new_session()["id"])["values"]["availability_date"], "2027-07-01")

    def test_three_version_buttons_have_distinct_effects(self):
        self.import_sample()
        initial = self.lab.state()["versions"][0]
        a, b = self.lab.new_session()["id"], self.lab.new_session()["id"]
        self.lab.edit_version(a, initial["id"], "session", "Only application A")
        self.assertEqual(self.lab.state()["versions"], [initial])
        self.assertEqual(self.lab.materials(a)["values"]["description"], "Only application A")
        self.assertEqual(self.lab.materials(b)["values"]["description"], initial["content"])
        self.lab.edit_version(a, initial["id"], "update", "Updated current version", 1)
        self.assertEqual(self.lab.state()["versions"][0]["revision"], 2)
        new = self.lab.edit_version(a, initial["id"], "new", "New separate version", name="方向 B")["version"]
        self.assertEqual(len(self.lab.state()["versions"]), 2)
        self.assertEqual(self.lab.materials(a)["values"]["description"], "New separate version")
        self.assertEqual(self.lab.materials(b)["values"]["description"], "Updated current version")
        self.assertNotEqual(new["id"], initial["id"])

    def test_stale_version_edit_is_rejected_without_overwrite(self):
        self.import_sample()
        version = self.lab.state()["versions"][0]
        session = self.lab.new_session()["id"]
        self.lab.edit_version(session, version["id"], "update", "Latest", 1)
        before = self.lab.state()
        with self.assertRaises(LabError) as error:
            self.lab.edit_version(session, version["id"], "update", "Stale", 1)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.lab.state(), before)

    def test_bad_dates_and_atomic_save_do_not_write_partial_values(self):
        self.lab.add_field({"id":"available","label":"到岗日期","category":"basic","type":"date"})
        entry = next(e for e in self.lab.state()["entries"] if e["category"]=="basic")
        before = self.lab.state()
        with self.assertRaises(LabError):
            self.lab.save_profile([{"entry_id":entry["id"],"field_id":"name","value":"Should roll back"},{"entry_id":entry["id"],"field_id":"available","value":"2027-02-30"}])
        self.assertEqual(self.lab.state(), before)

    def test_new_category_fields_and_manual_versions_do_not_need_a_resume(self):
        self.lab.add_field({"id":"custom_certificate_grade","label":"测试自定义等级","category":"certificates","type":"select","options":["一级","二级"]})
        one = self.lab.mutate(lambda state:self.lab.new_entry(state,"certificates"))
        two = self.lab.mutate(lambda state:self.lab.new_entry(state,"certificates"))
        self.assertNotEqual(one["id"],two["id"])
        self.lab.save_profile([{"entry_id":one["id"],"field_id":"custom_certificate_grade","value":"一级"}])
        with self.assertRaises(LabError):
            self.lab.save_profile([{"entry_id":two["id"],"field_id":"custom_certificate_grade","value":"三级"}])
        entry = self.lab.mutate(lambda state:self.lab.new_entry(state,"employment"))
        version = self.lab.create_version(entry["id"], "description", "Manual fictional description")
        self.assertEqual(version["content"], "Manual fictional description")
        self.assertFalse(self.lab.state()["files"])

    def test_changed_profile_cannot_be_overwritten_by_old_import_preview(self):
        preview = self.lab.upload("name.txt", b"Name: Candidate")
        candidate = preview["candidates"][0]
        entry = next(e for e in self.lab.state()["entries"] if e["category"]=="basic")
        self.lab.save_profile([{"entry_id":entry["id"],"field_id":"name","value":"Newer manual edit"}])
        with self.assertRaises(LabError) as error:
            self.lab.commit_import(preview["id"],[candidate["id"]],{},preview["revision"])
        self.assertEqual(error.exception.status,409)
        self.assertEqual(self.lab.materials(self.lab.new_session()["id"])["values"]["name"],"Newer manual edit")

    def test_http_upload_preview_commit_and_download_original(self):
        server = make_server(self.lab)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        def post(path, body):
            request=Request(base+path,json.dumps(body).encode(),{"Content-Type":"application/json"})
            return json.loads(urlopen(request).read())
        try:
            raw=(SAMPLES/"sample.pdf").read_bytes()
            preview=post('/api/import',{"filename":"sample.pdf","base64":base64.b64encode(raw).decode()})
            result=post('/api/import/commit',{"import_id":preview["id"],"accepted":[c["id"] for c in preview["candidates"] if c["selected"]]})
            self.assertEqual(result["saved"],13)
            self.assertEqual(urlopen(base+'/api/files/'+preview["file_id"]).read(),raw)
            self.assertIn('我的资料',urlopen(base).read().decode())
            with self.assertRaises(HTTPError) as error:
                post('/api/fields',{"label":"Invalid","category":"missing"})
            self.assertEqual(error.exception.code,400)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__ == '__main__':
    unittest.main(verbosity=2)
