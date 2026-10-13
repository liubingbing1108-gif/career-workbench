"""Opt-in real Codex test. Only fictional field definitions go to the model."""
import json
import tempfile
import time
from pathlib import Path
from lab import Lab
from application import Application
from mapping import WebsiteMapper


def run():
    with tempfile.TemporaryDirectory(prefix='profile-live-requirements-') as folder:
        lab=Lab(folder)
        try:
            for cat,values in [('education',dict(school='甲高中',degree='高中',graduation_date='2018-06')),('education',dict(school='乙大学',degree='本科',graduation_date='2022-06')),('education',dict(school='丙大学',degree='硕士',graduation_date='2027-06')),('employment',dict(company='实习单位',employment_type='实习')),('employment',dict(company='全职单位',employment_type='全职'))]:
                entry=lab.mutate(lambda s:lab.new_entry(s,cat));lab.save_profile([dict(entry_id=entry['id'],field_id=k,value=v) for k,v in values.items()])
            fields=[
                dict(id='college',label='学习经历',collection=True,required=True,instructions='请从本科起填写全部教育经历，不填写高中。',children=[dict(id='college_school',label='院校名称',required=True)]),
                dict(id='high_school',label='教育背景',collection=True,required=True,instructions='请从高中起填写全部教育经历。',children=[dict(id='hs_school',label='学校',required=True)]),
                dict(id='highest',label='最高学历院校',required=True,instructions='包含正在就读的最高学历，填写对应学校，不是只填已获得的学历'),
                dict(id='bachelor',label='本科毕业院校',required=True),
                dict(id='full_work',label='工作履历',collection=True,required=True,instructions='填写全部全职工作，不含实习。',children=[dict(id='work_company',label='单位',required=True)]),
                dict(id='selected_internships',label='实习经历',collection=True,required=True,instructions='可按个人意愿选择有代表性的实习经历，多段可新增。',children=[dict(id='intern_company',label='公司名称',required=True)]),
                dict(id='mentor',label='研究生导师姓名',required=True),
            ]
            class RecordedMapper(WebsiteMapper):
                def map(self, fields, profile):
                    result=super().map(fields, profile)
                    Path('/tmp/profile-fictional-requirements-mapping.json').write_text(json.dumps(result,ensure_ascii=False))
                    return result
            mapper=RecordedMapper();app=Application(lab,mapper);sid=lab.new_session()['id'];start=time.monotonic()
            app.scan(sid,dict(url='http://localhost/fictional-live',fields=fields));p=app.plan(sid)
            by_id={i['website_field']['id']:i['value'] for i in p['payload']}
            assert [r['school'] for r in by_id['college']]==['乙大学','丙大学'], by_id.get('college')
            assert {r['school'] for r in by_id['high_school']}=={'甲高中','乙大学','丙大学'}
            assert by_id['highest']=='丙大学' and by_id['bachelor']=='乙大学'
            assert [r['company'] for r in by_id['full_work']]==['全职单位']
            assert [r['company'] for r in by_id['selected_internships']]==['实习单位']
            assert [i['website_field']['id'] for i in p['decisions']]==['selected_internships']
            m=next(m for m in p['website']['mappings'] if m['website_id']=='mentor')
            assert m['status']=='new' and m['category']=='education'
            saved=app.edit_answer(sid,'mentor','虚构导师','update');master=next(e for e in lab.state()['entries'] if e['values'].get('school')=='丙大学')
            assert saved['entry_id']==master['id']
            assert app.plan(sid)['ready']
            print(json.dumps(dict(passed=8,model='existing Codex',seconds=round(time.monotonic()-start,3),scenarios=['本科起集合','高中起集合','最高学历','本科院校','全部全职','自选实习','只呈现实习选择','新导师归属研究生']),ensure_ascii=False),flush=True)
        finally:
            lab.db.close()

if __name__=='__main__':run()
