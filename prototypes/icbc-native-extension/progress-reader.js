/* Read only application records. Navigation is limited to visible account/record links. */
(function(root){
 const labels=['投递记录','我的投递','我的申请','申请记录','应聘记录','我的应聘','投递进度','我的求职','个人中心'];
 const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const clean=s=>String(s||'').replace(/\s+/g,'').replace(/^第\d+志愿/,'').replace(/^(?:校园招聘|校招|社招)[-—·：:]?/,'');
 const stagePattern=/筛选|评估|评审|审核|笔试|测评|面试|一面|二面|三面|终面|offer|录用|未通过|不合适|淘汰|结束|终止|撤回|放弃|处理中|待处理|待安排|已投递|已申请|已提交/i;
 function scope(value){const u=new URL(value),parts=u.pathname.split('/').filter(Boolean);return u.origin+(u.hostname.endsWith('mokahr.com')?'/'+parts.slice(0,3).join('/'):u.hostname.endsWith('.jobs.feishu.cn')?'/'+parts[0]:'');}
 function read(job){
  const url=location.href;if(scope(url)!==scope(job.url))return {status:'unavailable',url,records:[]};
  const visibleText=document.body?.innerText||'';
  if([...document.querySelectorAll('input[type=password]')].some(visible)||/请先登录|登录后查看|扫码登录|验证码登录|请完成验证/.test(visibleText)&&!document.querySelector('[class*=application-card]'))return {status:'needs_user',url,records:[]};
  const nodes=[...document.querySelectorAll('a,button,[role=button],[role=tab],li,span,div')].filter(visible);
  const nav=labels.map(label=>nodes.find(e=>e.textContent.trim()===label&&!e.closest('form'))).filter(Boolean).map(e=>({label:e.textContent.trim(),url:e.matches('a[href]')?e.href:''}));
  const records=[],seen=new Set();
  const titles=[...document.querySelectorAll('h1,h2,h3,h4,a,span,strong,td,div')].filter(e=>visible(e)&&clean(e.textContent)===clean(job.role)&&![...e.children].some(c=>clean(c.textContent)===clean(job.role)));
  for(const title of titles){
   let parent=title.parentElement;
   for(let n=0;parent&&n<6;n++,parent=parent.parentElement){
    if(parent.matches('body,main,form')||parent.querySelector('input:not([type=hidden]),textarea'))break;
    const text=parent.innerText||'';if(text.length>2000)break;
    const statuses=[...parent.querySelectorAll('[class*=status],[class*=Status],[class*=progress],[data-stage],td,dd')].filter(visible).map(e=>e.innerText?.trim()).filter(t=>t&&t.length<=60&&stagePattern.test(t)&&clean(t)!==clean(job.role));
    const explicit=[...parent.querySelectorAll('span,div,p')].filter(visible).map(e=>(e.innerText||'').trim().match(/^状态\s*[:：]\s*(.{1,60}?)(?:\s+项目\s*[:：][\s\S]*)?$/)?.[1]).filter(t=>t&&stagePattern.test(t));
    const unique=[...new Set([...statuses.map(t=>t.replace(/^状态\s*[:：]\s*/,'').split(/\s+项目\s*[:：]/)[0]),...explicit])];
    // Do not treat a status elsewhere on a resume or a page's navigation as a record.
    const record=/(?:application|record|apply|candidate|delivery|card|list-item)/i.test(parent.className||'')||parent.matches('tr,[role=row]')||/投递时间|申请时间|投递于|申请于|应聘职位|修改申请/.test(text);
    if(record&&unique.length===1){if(!seen.has(parent)){seen.add(parent);records.push({role:title.textContent.trim(),stage:unique[0]});}break;}
   }
  }
  const recordsPage=/\/candidateHome\/applications(?:[?&#/]|$)/i.test(url)&&/状态\s*[:：]/.test(visibleText);
  return {status:records.length||recordsPage?'records':'unavailable',url,records,nav};
 }
 function navigate(job,label,expected){
  if(location.href!==expected||scope(location.href)!==scope(job.url)||!labels.includes(label))throw Error('查询页面已变化');
  const matches=[...document.querySelectorAll('a,button,[role=button],[role=tab],li,span,div')].filter(e=>visible(e)&&e.textContent.trim()===label&&!e.closest('form'));
  const chosen=matches.find(e=>e.matches('a,button,[role=button]'))||matches.find(e=>![...e.children].some(c=>c.textContent.trim()===label));
  if(!chosen)throw Error('投递记录入口已变化');
  const link=chosen.closest('a[href]');if(link){const u=new URL(link.href);if(u.protocol!=='https:'||scope(u.href)!==scope(job.url))throw Error('投递记录入口不属于本招聘网站');}
  chosen.click();return true;
 }
 root.JobProgressReader={read,navigate,scope};
})(globalThis);
