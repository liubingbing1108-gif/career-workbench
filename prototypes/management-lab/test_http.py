import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import feishu
from server import App, handler


def fixture():
    return {"fetched_at":"2026-10-11T00:00:00+08:00", "test_fixture": True, "base":{"name":"界面验证（虚构）","url":"https://example.com/fixture"},
            "permissions":{"read_verified":False,"edit_verified":False,"remote_write_enabled":False},"workflows":[],"tables":[
                {"kind":"applications","name":"虚构历史表","id":"fictional-table","count":2,"fields":[],"records":[
                    {"record_id":"fictional-single","fields":{"公司名称":"虚构甲公司","岗位名称":"虚构分析岗位","投递链接":"https://example.com/a","面试进度":["已投递"]}},
                    {"record_id":"fictional-summary","fields":{"公司名称":"虚构乙公司","岗位名称":"虚构岗位甲、虚构岗位乙","投递链接":"https://example.com/b","面试进度":["二面"]}}]}]}


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="management-http-test-")
        feishu.save_snapshot(fixture(),self.tmp.name)
        self.app=App(self.tmp.name)
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,method,path,body=None,token=True,origin=None):
        con=http.client.HTTPConnection("127.0.0.1",self.server.server_port)
        headers={"Content-Type":"application/json"}
        if token:headers["X-Management-Token"]=self.app.token
        if origin:headers["Origin"]=origin
        con.request(method,path,json.dumps(body) if body is not None else None,headers)
        response=con.getresponse();raw=response.read();status=response.status;con.close()
        return status,json.loads(raw)
    def test_bootstrap_has_real_scope_and_no_implicit_remote_calls(self):
        with patch("feishu.cli") as cli:
            status,data=self.request("GET","/api/bootstrap")
            self.assertEqual(status,200);self.assertNotIn('source',data)
            self.assertFalse(data["remote_write_enabled"]);cli.assert_not_called()

    def test_explicit_dynamic_link_preview_confirm_and_readback(self):
        url='https://sample.jobs.feishu.cn/123456/resume/1234567890123456789/apply'
        with patch.object(self.app.intake,'read_sources',side_effect=AssertionError('unexpected network')):
            status,preview=self.request('POST','/api/preview/text',{'text':url+'\n示例科技 用户增长产品经理（平台运营）'})
        self.assertEqual(status,200)
        self.assertEqual(self.app.store.list_jobs(),[])
        candidate=preview['candidates'][0]
        self.assertEqual((candidate['company'],candidate['role']),('示例科技','用户增长产品经理（平台运营）'))
        body={'source':'text','batch_id':preview['batch_id'],'selections':[{'id':candidate['id']}],'request_id':'dynamic-link-confirmed-fixture'}
        status,result=self.request('POST','/api/import',body)
        self.assertEqual(status,200)
        self.assertTrue(self.request('POST','/api/import',body)[1]['replayed'])
        status,job=self.request('GET','/api/jobs/'+result['ids'][0])
        self.assertEqual(status,200);self.assertEqual(job['source_url'],url)
        self.assertEqual(job['official_url'],'');self.assertFalse(job['needs_review'])
        self.assertEqual(job['application_status'],'未投递');self.assertEqual(job['timeline'],[])
    def test_cross_origin_or_missing_token_cannot_mutate(self):
        self.assertEqual(self.request("POST","/api/preview/text",{"text":"x"},token=False)[0],403)
        self.assertEqual(self.request("POST","/api/preview/text",{"text":"x"},origin="https://example.com")[0],403)
    def test_split_preview_does_not_import_or_assign_summary_stage(self):
        preview=self.app.store.save_preview(feishu.candidates(fixture()))
        status,data=self.request("POST","/api/preview/split",{"batch_id":preview['batch_id'],"candidate_id":"applications:fictional-summary","roles":["虚构岗位甲","虚构岗位乙"]})
        self.assertEqual(status,200);self.assertEqual(len(data["candidates"]),2)
        self.assertTrue(all(c["recruitment_stage"]=="" for c in data["candidates"]))
        self.assertEqual(self.app.store.list_jobs(),[])
    def test_query_unavailable_preserves_status_stage_and_dates(self):
        c=feishu.candidates(fixture())[0]
        jid=self.app.store.import_selected([c],[{"id":c["id"]}],"fictional-request",{})["ids"][0]
        before=self.app.store.get(jid)
        with patch("feishu.cli") as cli:
            status,result=self.request("POST","/api/jobs/"+jid+"/query",{})
            self.assertEqual(status,200);self.assertFalse(result["changed"]);cli.assert_not_called()
        self.assertEqual(before,self.app.store.get(jid))
    def test_missing_write_routes_are_closed(self):
        self.assertEqual(self.request("POST","/api/feishu/write",{})[0],404)
    def test_unresolved_official_lookup_does_not_change_job(self):
        c=feishu.candidates(fixture())[0]
        jid=self.app.store.import_selected([c],[{'id':c['id']}],'fictional-unresolved',{})['ids'][0]
        before=self.app.store.get(jid)
        with patch.object(self.app.official,'lookup',return_value={'status':'needs_selection','candidates':[]}):
            status,result=self.request('POST','/api/jobs/'+jid+'/resolve',{})
        self.assertEqual(status,200);self.assertEqual(result['status'],'needs_selection')
        self.assertEqual(before,self.app.store.get(jid))
    def test_official_entry_http_requires_token_and_current_revision(self):
        c=feishu.candidates(fixture())[0]
        jid=self.app.store.import_selected([c],[{'id':c['id']}],'fictional-official',{})['ids'][0]
        job=self.app.store.get(jid)
        entry={'company':job['company'],'role':job['role'],'location':'',
               'company_url':'https://example.com/','recruitment_url':'https://example.com/careers',
               'url':'https://example.com/official-role','verification':'browser',
               'evidence':[{'url':'https://example.com/','quote':job['company']},
                           {'url':'https://example.com/official-role','quote':job['role']}]}
        body={'revision':job['revision'],'entry':entry};route='/api/jobs/'+jid+'/official'
        self.assertEqual(self.request('POST',route,body,token=False)[0],403)
        self.assertEqual(self.request('POST',route,{**body,'entry':{**entry,'role':'其他岗位'}})[0],400)
        status,saved=self.request('POST',route,body)
        self.assertEqual(status,200);self.assertEqual(saved['source_url'],job['url'])
        self.assertEqual(saved['timeline'],job['timeline'])
        self.assertEqual(self.request('POST',route,body)[0],409)

    def test_embedded_routes_reuse_the_same_store_without_implicit_import(self):
        status,data=self.request("GET","/management/api/bootstrap")
        self.assertEqual(status,200)
        self.assertNotIn('source',data)
        self.assertEqual(data["jobs"],[])
        status,preview=self.request("POST","/management/api/preview/text",{"text":"虚构公司 | 虚构岗位 | https://example.com/apply"})
        self.assertEqual(status,200)
        self.assertEqual(self.app.store.list_jobs(),[])
        status,result=self.request("POST","/management/api/import",{"source":"text","batch_id":preview["batch_id"],"selections":[{"id":preview["candidates"][0]["id"]}],"request_id":"embed-fictional-selection"})
        self.assertEqual(status,200)
        status,jobs=self.request("GET","/api/jobs")
        self.assertEqual(status,200)
        self.assertEqual([j["id"] for j in jobs["jobs"]],result["ids"])
        self.assertEqual(jobs["jobs"][0]["timeline"],[])
        self.assertEqual(jobs["jobs"][0]["application_status"],"未投递")
        self.assertEqual(jobs["jobs"][0]["recruitment_stage"],"")

    def test_embedding_has_relative_assets_and_same_origin_frame_policy(self):
        con=http.client.HTTPConnection("127.0.0.1",self.server.server_port)
        con.request("GET","/management/?embedded=1")
        response=con.getresponse();html=response.read().decode()
        self.assertEqual(response.status,200)
        self.assertIn("frame-ancestors 'self'",response.getheader("Content-Security-Policy"))
        self.assertIn('href="./style.css"',html)
        self.assertIn('src="./app.js"',html)
        self.assertIn('src="./integration.js"',html)
        self.assertNotIn('<nav',html)
        for asset in ("style.css","app.js","integration.js"):
            con.request("GET","/management/"+asset)
            response=con.getresponse();response.read()
            self.assertEqual(response.status,200)
        con.request("GET","/management?embedded=1")
        response=con.getresponse();response.read()
        self.assertEqual(response.status,302)
        self.assertEqual(response.getheader("Location"),"/management/?embedded=1")
        con.close()

    def test_embedded_mutations_keep_token_and_origin_checks(self):
        self.assertEqual(self.request("POST","/management/api/preview/text",{"text":"x"},token=False)[0],403)
        self.assertEqual(self.request("POST","/management/api/preview/text",{"text":"x"},origin="https://example.com")[0],403)
        self.assertEqual(self.request("POST","/management/api/feishu/write",{})[0],404)


if __name__=='__main__':unittest.main(verbosity=2)
