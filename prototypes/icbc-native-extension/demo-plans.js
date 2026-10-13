/* Explicit synthetic fixtures. Never imported by executor-core or a site adapter. */
window.JobFillDemo={
 fill(snapshot){
  const targetFields=snapshot.fields.filter(f=>f.sectionId==='education'&&f.recordId==='education[1]'||f.fieldId==='internship[1].desc'||f.fieldId==='award[1].title');
  const sample={school:'清华大学',degree:'硕士',fieldOfStudy:'软件工程',periodInputBegin:'2023-09',periodInputEnd:'2025-06'};
  return {method:'execute',payload:{schemaVersion:1,requestId:'demo-'+crypto.randomUUID(),snapshotId:snapshot.snapshotId,assignments:targetFields.map(f=>({fieldId:f.fieldId,value:f.fieldId.startsWith('education')?sample[f.fieldId.split('.')[1].replace(/Input$/,'')]:f.fieldId.startsWith('internship')?'接口封装后的新增实习测试描述，仅用于功能验证。':'接口封装测试奖项',overwrite:'ifUnchanged',sourceRef:'synthetic-demo/'+f.fieldId}))}};
 },
 records(snapshot){return {method:'ensureRecords',payload:{schemaVersion:1,requestId:'records-'+crypto.randomUUID(),snapshotId:snapshot.snapshotId,sections:snapshot.sections.filter(s=>['education','internship','award','project'].includes(s.sectionId)).map(s=>({sectionId:s.sectionId,count:s.count}))}};}
};
