/* Proven ICBC controls, now parameterized. No fixed resume answers. */
(()=>{'use strict';let activeContext=null;
 const sections=['教育经历','语言能力','荣誉或奖励','学术成果','资格认证','工作（实习）经历','自我评价','家庭关系','工作意向'];
 const q=(selector,root=document)=>[...root.querySelectorAll(selector)];
 const txt=e=>e?.textContent?.trim()||'';
 const visible=e=>!!e?.isConnected&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const one=(elements,why)=>{if(elements.length!==1)throw new Error(why+'：匹配数量 '+elements.length);return elements[0];};
 const buttons=name=>q('button').filter(e=>visible(e)&&txt(e)===name);
 const active=()=>txt(document.querySelector('[class*="menu__item--active"]'));
 const value=c=>txt(c.querySelector('.ant-select-selection-selected-value'))||q('.ant-select-selection__choice__content',c).map(txt).join('、');
 let panel=document.querySelector('#jobfill-executor-progress');
 function guard(){
  
  if(location.protocol!=='https:'||location.hostname!=='job.icbc.com.cn'||location.pathname!=='/pc/index.html'||location.hash!=='#/main/resumeEdit'||txt(document.querySelector('h1'))!=='实习生简历')throw new Error('仅允许实习生简历编辑页');
  if(document.body.innerText.includes('登录超时，请重新登录')||q('input[type=password]').some(visible))throw new Error('请在当前标签页登录');
  if(!sections.some(name=>active().startsWith(name)))throw new Error('仅允许九个普通分区，请先在官网打开相应分区');
 }
 const wait=(fn,ms=12000)=>new Promise((resolve,reject)=>{const start=performance.now();const tick=()=>{try{activeContext?.check();guard();const result=fn();if(result)return resolve(result);if(performance.now()-start>=ms)throw new Error('等待官网状态超时');setTimeout(tick,30);}catch(e){reject(e);}};tick();});
 function show(message){
  if(!panel){panel=document.createElement('aside');panel.id='jobfill-executor-progress';panel.style.cssText='position:fixed;right:14px;bottom:14px;max-width:390px;padding:15px;background:#152338;color:white;z-index:2147483647;font:14px/1.6 system-ui;box-shadow:0 4px 20px #0005';document.body.append(panel);}
  panel.textContent=message;panel.style.pointerEvents='none';
 }
 const click=e=>{if(!visible(e)||e.disabled)throw new Error('控件不可操作');e.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));e.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));e.click();};
 function setText(e,v,blur=true){
  if(e.disabled||e.readOnly)throw new Error('文本控件不可写');
  e.focus();const p=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(p,'value').set.call(e,String(v));
  e.dispatchEvent(new Event('input',{bubbles:true,composed:true}));e.dispatchEvent(new Event('change',{bubbles:true,composed:true}));if(blur)e.blur();
 }
 const errors=()=>q('.ant-form-explain').filter(visible).map(txt);
 function scan(){
  guard();const fields=[];
  q('.ant-form-item').filter(visible).forEach((item,index)=>{
   const label=txt(item.querySelector('.ant-form-item-label'));const base=item.querySelector('label')?.htmlFor||label||'dates-'+index;
   const push=f=>fields.push({...f,item,index});
   q('[role=combobox]',item).forEach((el,part)=>push({key:base+'/select/'+part,label,part,el,kind:el.className.includes('--multiple')?'multiselect':'select',disabled:!!el.closest('.ant-select-disabled'),current:el.className.includes('--multiple')?q('.ant-select-selection__choice__content',el).map(txt):value(el)}));
   const radios=q('input[type=radio]',item);
   if(radios.length)push({key:base+'/radio',label,kind:'radio',el:radios[0],disabled:radios.every(e=>e.disabled),current:txt(radios.find(e=>e.checked)?.closest('label'))});
   q('.ant-calendar-picker-input',item).forEach((el,part)=>push({key:base+'/date/'+part,label:label||txt(el.closest('.ant-calendar-picker')?.parentElement.querySelector('[class*=picker__label]'))||el.placeholder,part,el,kind:'date',disabled:el.disabled,current:el.value,placeholder:el.placeholder}));
   q('input,textarea',item).filter(e=>!e.closest('.ant-select')&&!e.matches('.ant-calendar-picker-input')&&!['radio','checkbox','file','hidden'].includes(e.type)).forEach((el,part)=>push({key:base+'/text/'+part,label,part,el,kind:'text',disabled:el.disabled||el.readOnly,current:el.value}));
  });return fields;
 }
 async function ready(settle=true){
  await wait(()=>{const save=buttons('保 存')[0];const loading=q('div,span').some(e=>visible(e)&&e.childElementCount===0&&txt(e)==='加载中，请稍后');return save&&!save.disabled&&!loading;});
  if(!settle){guard();return;}
  // Wait for DOM quiet; no app internals or arbitrary long sleep.
  await new Promise((resolve,reject)=>{let timer;const deadline=setTimeout(()=>{o.disconnect();clearTimeout(timer);reject(new Error('页面持续重绘'));},5000);const done=()=>{o.disconnect();clearTimeout(deadline);resolve();};const arm=()=>{clearTimeout(timer);timer=setTimeout(done,120);};const o=new MutationObserver(records=>{if(records.some(r=>!panel?.contains(r.target)))arm();});o.observe(document.body,{subtree:true,childList:true,attributes:true,characterData:true});arm();});
  guard();
 }
 async function go(name){
  if(active().startsWith(name)){await ready();return;}
  const old=document.querySelector('.ant-form-item label[for]');const oldFor=old?.htmlFor;
  click(one(q('li').filter(e=>visible(e)&&txt(e).startsWith(name)),'分区 '+name));
  await wait(()=>active().startsWith(name)&&(!old||!old.isConnected||!visible(old)||old.htmlFor!==oldFor));await ready();
 }

 function fields(){return scan().map(f=>({...f,id:f.key,sectionId:active(),recordId:f.key.match(/#[0-9]+/)?.[0]||'',required:!!f.item.querySelector('.ant-form-item-required'),description:txt(f.item.querySelector('.ant-form-extra')),constraints:{...(f.el.maxLength>0?{maxLength:f.el.maxLength}:{})},options:{state:['select','multiselect'].includes(f.kind)?'requires-opening':'not-applicable',items:[]},kind:f.kind==='date'?(/^\d{4}$/.test(f.current)?'year':/^\d{4}-\d{2}$/.test(f.current)?'month':f.el.placeholder?.includes('年')&&!f.el.placeholder?.includes('月')?'year':f.el.placeholder?.includes('月')&&!f.el.placeholder?.includes('日')?'month':'date'):f.kind}));}
 async function write(f,expected,ctx){
  activeContext=ctx;ctx.check();if(f.disabled)throw Error('字段不可写');
  if(f.kind==='text')setText(f.el,expected);
  else if(f.kind==='radio'){
   const choices=q('input[type=radio]',f.item).filter(e=>!e.disabled&&txt(e.closest('label'))===expected);const target=one(choices,'单选选项');if(!target.checked)click(target);
  }else if(f.kind==='select'||f.kind==='multiselect'){
   click(f.el);const menu=await wait(()=>q('.ant-select-dropdown').find(visible));
   const search=q('.ant-select-search__field',f.item).find(visible);
   if(search&&f.kind==='select'&&/学校名称/.test(f.label))setText(search,expected,false);
   if(f.kind==='multiselect'){
    // Toggle only observed options; never silently append to an existing set.
    const selected=q('.ant-select-selection__choice__content',f.el).map(txt);
    for(const optionText of [...new Set([...selected,...expected])]){
     const want=expected.includes(optionText);if(selected.includes(optionText)===want)continue;
     const option=await wait(()=>{const a=q('[role=option]',menu).filter(e=>visible(e)&&!e.className.includes('disabled')&&txt(e)===optionText);return a.length?one(a,'多选选项'):null;});click(option);
    }
    document.activeElement?.blur();click(document.querySelector('h1'));
   }else{
    const option=await wait(()=>{const a=q('[role=option]',menu).filter(e=>visible(e)&&!e.className.includes('disabled')&&txt(e)===expected);return a.length?one(a,'下拉选项'):null;});click(option);
   }
   await wait(()=>!visible(menu));
  }else if(['date','month','year'].includes(f.kind)){
   click(f.el);const popup=await wait(()=>q('.ant-calendar-picker-container').find(visible));const entry=q('.ant-calendar-input',popup).find(visible);
   if(entry){setText(entry,expected,false);entry.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));document.activeElement?.blur();click(document.querySelector('h1'));}
   else{
    const cells=q('td',popup).filter(e=>visible(e)&&!e.className.includes('disabled'));
    const dateParts=expected.split('-'),monthNames=['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月'];
    const wanted=dateParts.length===1?expected:monthNames[Number(dateParts[1])-1];
    const candidates=cells.filter(e=>txt(e)===wanted);
    // For month-only calendars reject a different year instead of guessing navigation.
    if(dateParts.length>1&&!txt(popup).includes(dateParts[0]))throw Error('该月份面板年份不匹配，需人工切换后重新扫描');
    click(one(candidates,'日期单元'));
   }
   await wait(()=>!visible(popup));
  }else throw Error('未适配控件');
  await wait(()=>JSON.stringify(fields().find(x=>x.id===f.id)?.current)===JSON.stringify(expected),3500);
 }
 async function save(){
  await ready(false);const before=new Set(q('.ant-message-notice'));
  click(one(buttons('保 存'),'保存按钮'));
  await wait(()=>q('.ant-message-notice').some(e=>!before.has(e)&&visible(e)&&txt(e).includes('保存成功')),15000);
  await ready(false);if(errors().length)throw new Error('官网校验失败：'+errors().join('；'));
 }
 window.JobFillAdapters=window.JobFillAdapters||{};
 window.JobFillAdapters.icbc={id:'icbc-intern',guard,page:()=>({adapter:'icbc-intern',url:location.href,title:txt(document.querySelector('h1')),section:active()}),fields,sections:()=>sections.map(sectionId=>({sectionId,label:sectionId,canAdd:false})),write,errors,show,saveDraft:async ctx=>{activeContext=ctx;await save();},settle:async ctx=>{activeContext=ctx;await window.JobFillDOM.settle(errors,ctx);},openSection:async (name,ctx)=>{if(!sections.includes(name))throw Error('不支持的分区');activeContext=ctx;await go(name);}};
})();
