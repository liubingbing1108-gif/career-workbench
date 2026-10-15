"""Approved P9–P24 profile contract. UI modules reuse legacy record/field IDs."""
import copy

MODULES = [
 ('basic','基本身份',['basic','identity_documents']),('contact','联系与地址',['contact','social']),
 ('education','教育经历',['education']),('employment','实习与工作',['employment']),
 ('projects','项目与研究',['projects']),('campus','活动经历',['campus']),
 ('language','语言与考试',['language']),('skills','技能与资格',['skills','certificates']),
 ('honors','荣誉与奖励',['honors']),('academic','学术成果与作品',['academic','portfolio']),
 ('family','家庭与联系人',['family']),('preferences','求职意向',['preferences']),
 ('subjective','个人陈述',['subjective']),('attachments','文件附件',['attachments'])]
RECORD_TYPES = {'language': [('ability','语言能力'),('exam','语言考试')],
 'academic': [('paper','论文'),('patent','专利')], 'portfolio':[('work','作品'),('homepage','个人/代码主页')]}
FIELDS=[]
def group(cat, title, spec, *, extra=False, types=None):
    for token in spec.split('|'):
        key,label,*kind=token.split(':')
        typ=kind[0] if kind else 'text'
        widget=typ if typ in ('boolean','file','files') else None
        FIELDS.append(dict(id=key,label=label,category=cat,type='text' if widget else typ,
            widget=widget,group=title,supplemental=extra,record_types=types or [],aliases=[],options=[]))

group('basic','姓名','name:中文姓名|surname:姓|given_name:名|name_pinyin:姓名拼音|english_name:英文名|former_name:曾用名')
group('basic','身份','gender:性别|birth_date:出生日期:partial_date|nationality:国籍/地区|ethnicity:民族|political_status:政治面貌|political_joined:入党/团日期:partial_date|marital_status:婚姻状况|native_place:籍贯|student_origin:生源地')
group('basic','照片','life_photo:生活照:file|id_photo:证件照:file')
group('basic','补充信息','height_cm:身高（厘米）:number|weight_kg:体重（千克）:number|health_status:健康情况',extra=True)
group('identity_documents','身份证件','identity_type:证件类型|identity_number:证件号码|identity_valid_from:有效起始日期:partial_date|identity_valid_until:有效截止日期:partial_date')
group('contact','电话与邮箱','phone:主用手机|phone_code:主用手机区号|backup_phone:备用电话|backup_phone_code:备用电话区号|email:主用邮箱|backup_email:备用邮箱')
for prefix,label in [('residence','现居地址'),('hukou','户籍地址'),('mailing','通讯地址')]:
 group('contact',label,'|'.join(f'{prefix}_{key}:{label}·{name}' for key,name in [('country','国家/地区'),('province','省'),('city','市'),('district','区县'),('address','详细地址'),('postcode','邮编')]))
group('social','联系账号','social_platform:平台|social_account:账号')
group('education','学校与专业','school:学校名称|college:学院/院系|school_location:学校所在地|major:专业名称|major_category:专业类别|minor_major:第二专业/辅修专业')
group('education','学历与学位','degree:学历层次|degree_name:学位名称|study_mode:学习形式|double_degree:是否双学位:boolean|training_mode:培养方式')
group('education','时间与状态','education_started:入学日期:partial_date|graduation_date:毕业时间:partial_date|study_status:在读/毕业/结业状态|degree_status:学位取得状态|degree_awarded:学位取得日期:partial_date')
group('education','学习成绩','gpa:GPA|gpa_max:GPA满分|average_score:平均成绩|average_score_max:平均成绩满分|rank:排名名次|rank_total:排名总人数|rank_scope:排名范围')
group('education','学习内容','courses:主修课程:multiline|research_direction:研究方向|advisor:导师|thesis_title:毕业论文题目|education_description:教育经历完整说明:versioned_text')
group('education','补充信息','student_number:学号|graduation_certificate:毕业证编号|degree_certificate:学位证编号|exchange_description:交换/联合培养说明:multiline|education_files:成绩单及学历/学位证明:files',extra=True)
group('employment','单位与职位','company:单位名称|department:部门|role:职位名称|employment_type:经历性质|employment_location:工作地点')
group('employment','时间与状态','started:开始时间:partial_date|ended:结束时间:partial_date|still_employed:是否仍在职:boolean')
group('employment','经历内容','description:完整经历描述:versioned_text|responsibilities:工作职责:multiline|achievements:工作成果:multiline')
group('employment','单位补充','industry:所属行业|company_type:单位性质|company_size:单位规模',extra=True)
group('employment','其他补充','leaving_reason:离职原因|reference_name:证明人姓名|reference_role:证明人职位|reference_contact:证明人联系方式|employment_files:证明附件:files',extra=True)
group('projects','项目基本信息','project_name:项目名称|project_type:项目类型|project_organization:所属单位/学校|project_location:项目地点')
group('projects','时间与角色','project_started:开始时间:partial_date|project_ended:结束时间:partial_date|project_ongoing:是否仍在进行:boolean|project_role:本人角色/职务|project_team_size:团队人数:number')
group('projects','项目内容','project_description:完整项目描述:versioned_text|project_background:项目背景/目标:multiline|project_responsibilities:本人职责:multiline|project_process:实施过程:multiline|project_results:项目成果:multiline')
group('projects','技术与材料','project_tools:使用工具/技术/方法|project_link:项目/作品链接|project_files:相关附件:files')
group('campus','活动基本信息','campus_title:活动名称|activity_type:活动类型|activity_organization:组织/主办单位|activity_location:活动地点')
group('campus','时间与角色','campus_started:开始时间:partial_date|campus_ended:结束时间:partial_date|activity_ongoing:是否仍在进行:boolean|activity_role:本人角色/职务')
group('campus','活动内容','campus_description:完整活动描述:versioned_text|activity_responsibilities:本人职责:multiline|activity_results:活动成果:multiline')
group('campus','补充信息','activity_duration:参与/服务时长|activity_duration_unit:时长单位|activity_files:证明附件:files',extra=True)
group('language','语言能力','language_name:语种|language_level:总体熟练程度|listening:听力水平|speaking:口语水平|reading:阅读水平|writing:写作水平|language_description:能力说明:multiline',types=['ability'])
group('language','语言考试','exam_name:考试名称|exam_language:考试语种|exam_level:考试等级|exam_date:考试日期:partial_date|language_score:总分|exam_subscores:分项成绩（项目名与成绩）:multiline|exam_number:证书/成绩单编号|exam_validity:有效期|exam_files:成绩证明附件:files',types=['exam'])
group('skills','技能','skill_name:技能名称|skill_category:技能类别|skill_level:熟练程度|skill_years:使用年限|skill_description:技能说明:multiline')
group('certificates','资格证书','certificate_name:证书/资格名称|certificate_level:等级|certificate_issuer:颁发机构|certificate_date:取得日期:partial_date|certificate_validity:有效期|certificate_number:证书编号|certificate_progress:取得状态|certificate_subjects:已通过科目:multiline|certificate_files:证明附件:files')
group('honors','奖项信息','award_name:奖项名称|award_date:获奖时间|award_issuer:颁发单位|award_level:奖项级别|award_prize:获奖等次|award_subject:个人/团体|award_role:本人角色|award_details:完整获奖说明:multiline|award_files:证明附件:files')
group('academic','成果信息','academic_name:名称|academic_role:本人角色/作者排序|academic_description:完整说明:versioned_text|academic_link:链接|academic_files:附件:files')
group('academic','论文补充','journal:期刊/会议名称|publication_date:发表日期:partial_date|publication_status:发表状态|doi:DOI',types=['paper'])
group('academic','专利补充','patent_type:专利类型|patent_applied:申请日期:partial_date|patent_granted:授权日期:partial_date|patent_application_number:申请号|patent_number:专利号|patent_status:专利状态',types=['patent'])
group('portfolio','作品信息','portfolio_name:名称|portfolio_role:本人角色/作者排序|portfolio_description:完整说明:versioned_text|portfolio_link:链接|portfolio_files:附件:files|portfolio_type:作品类型|portfolio_platform:发布平台|portfolio_date:发布日期:partial_date|portfolio_number:登记号',types=['work'])
group('portfolio','个人/代码主页','homepage_platform:平台名称|homepage_url:主页地址',types=['homepage'])
group('family','基本信息','family_name:姓名|family_relation:与本人关系|contact_purpose:用途（家庭成员/紧急联系人/证明人）')
group('family','联系方式','family_phone:联系电话|family_phone_code:区号|family_email:邮箱')
group('family','工作信息','family_company:工作单位|family_role:职务|family_work_status:工作/退休状态')
group('family','补充信息','family_birth_date:出生日期:partial_date|family_political_status:政治面貌',extra=True)
group('preferences','方向与地点','preferred_role:意向岗位/方向|preferred_industry:意向行业|preferred_work_type:工作性质|preferred_cities:意向城市及优先顺序:multiline')
group('preferences','薪资','expected_salary:期望薪资或范围|salary_currency:币种|salary_period:计薪周期|salary_tax:税前/税后|salary_negotiable:是否面议:boolean')
group('preferences','到岗安排','available_date:最早到岗日期:partial_date|notice_period:离职通知期|internship_duration:可持续实习时长|days_per_week:每周可工作天数:number')
group('preferences','工作安排','accept_travel:是否接受出差:boolean|accept_other_city:是否接受异地工作:boolean|accept_relocation:是否接受工作地点调动:boolean')
group('subjective','个人陈述','statement_type:主题类型|statement_title:标题/具体问题|statement_content:完整正文:versioned_text|statement_language:语言|statement_scope:适用范围（通用/岗位方向/公司）|statement_role:适用岗位方向|statement_company:适用公司')

ALIASES={'name':['姓名','中文名'],'phone':['手机','手机号','电话'],'email':['邮箱','电子邮箱'],
 'degree_name':['学位'],'nationality':['国籍'],'school':['学校'],'degree':['学历'],'graduation_date':['毕业日期','预计毕业时间','预计毕业日期','实际毕业日期'],
 'description':['经历描述'],'company':['公司'],'role':['职位'],'started':['开始日期'],'ended':['结束日期'],
 'award_name':['荣誉名称'],'award_date':['获奖日期','获奖年月'],'award_details':['荣誉说明'],
 'campus_title':['校园经历名称'],'campus_description':['校园经历描述'],'language_score':['语言成绩'],
 'language_name':['语言／考试'],'certificate_progress':['完成情况'],'certificate_name':['证书名称'],
 'project_role':['项目角色','本人角色','担任角色','担任职务','项目职务'],
 'project_name':['项目名称','项目名'], 'project_description':['项目描述','项目说明','描述'],
 'project_started':['开始日期','开始时间','起止时间（开始）'],
 'project_ended':['结束日期','结束时间','起止时间（结束）'],
 'project_link':['项目链接','作品链接'],
 'activity_role':['活动角色','本人角色','担任角色','担任职务'],
 'campus_description':['校园经历描述','活动描述','活动说明'],
 'role':['职位','实习职位','担任职位','岗位名称'],
 'major':['专业','所学专业'], 'education_started':['入学时间','入学年月'],
 'statement_content':['个人陈述正文']}
for field in FIELDS:field['aliases']=ALIASES.get(field['id'],[])


def install(state):
    """Add definitions; never rewrite record values, IDs, versions or source files."""
    if state.get('library_contract',0)<24:
        state.setdefault('profile_legacy_single_entries',{cat:[e['id'] for e in state['entries'] if e['category']==cat and not e.get('profile_archived')] for cat in ('subjective','preferences')})
    state.setdefault('profile_field_links',{})
    for spec in FIELDS:
        field=next((f for f in state['fields'] if f['id']==spec['id']),None)
        if field is None:
            labels={spec['label'],*spec['aliases']}
            matches=[f for f in state['fields'] if f['category']==spec['category'] and f['label'] in labels]
            field=matches[0] if len(matches)==1 else None
        if field is None:
            field=copy.deepcopy(spec);state['fields'].append(field)
        else:
            old_label=field['label']
            for key in ('label','group','supplemental','record_types','widget'):field[key]=copy.deepcopy(spec[key])
            field['aliases']=list(dict.fromkeys([*field.get('aliases',[]),old_label,spec['label'],*spec['aliases']]))
            if field['type']=='date' and spec['type']=='partial_date':field['type']='partial_date'
        state['profile_field_links'][spec['id']]=field['id']
    state['profile_modules']=[dict(id=k,label=label,categories=cats) for k,label,cats in MODULES]
    state['profile_record_types']=copy.deepcopy(RECORD_TYPES)
    state.setdefault('profile_drafts',{})
    state['library_contract']=24
    from profile_hierarchy import install as install_hierarchy
    install_hierarchy(state)


def fields_for(state,entry):
    return [f for f in state['fields'] if f['category']==entry['category'] and (not f.get('entry_id') or f['entry_id']==entry.get('id')) and
        (not f.get('record_types') or not entry.get('record_type') or entry['record_type'] in f['record_types'] or f['id'] in entry.get('values',{}))]


def available(entry,session=None):
    return not entry.get('profile_archived') or entry['id'] in (session or {}).get('archived_profile_refs',[])
