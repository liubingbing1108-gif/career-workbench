/* Site control mechanics only. Values are supplied by the execution plan. */
(() => {
 'use strict';
 const {q,text,visible,one,click,setText,wait,show,settle}=window.JobFillDOM;
 const names={education:'教育经历',career:'工作经历',internship:'实习经历',project:'项目经历',work:'作品',award:'获奖',language:'语言能力',sns:'社交账号'};
 const originPage=location.href;
 function guard(){if(location.protocol!=='https:'||location.href!==originPage||!document.querySelector('.createFormSection-repeatable'))throw Error('表单已切换，请重新扫描');if(q('input[type=password]').some(visible))throw Error('请本人登录');}

 const outside=()=>{document.activeElement?.blur();click(one(q('.createFormSection-text').filter(e=>visible(e)&&text(e)==='教育经历'),'教育标题'));};
 function current(f){
  if(['text','year'].includes(f.kind))return f.el.value;
  if(f.kind==='month'){const v=text(f.el).replace(/\s+/g,'');return /YYYY|MM/.test(v)?'':v;}
  if(['select','autocomplete'].includes(f.kind))return text(f.el.querySelector('.atsx-select-selection-selected-value'))||f.el.querySelector('input')?.value||'';
  return text(f.item.querySelector('.ud__select__selector__content'));
 }
 function sections(){return Object.entries(names).flatMap(([sectionId,label])=>{const root=q('.resumeEditForm-'+sectionId+'.createFormSection-repeatable').find(visible);return root?[{sectionId,label,count:q('.resumeEditForm-item',root).length,canAdd:q('.formOperate-addBtn,.createFormSection-addBtn',root).some(visible)}]:[];});}
 function fields(){guard();const out=[];
  for(const item of q('.atsx-form-item').filter(visible)){
   const label=text(item.querySelector('.atsx-form-item-label label'));if(!label||['内推码','意向城市','手机号码','作品附件'].includes(label))continue;
   const sectionId=Object.keys(names).find(s=>item.closest('.resumeEditForm-'+s))||'basic';
   const add=(el,kind)=>{
    const id=el.id||el.getAttribute('data-cy'),recordId=id?.match(/^([^[]+\[\d+\])/ )?.[1]||'';
    const f={id,label,kind,el,item,sectionId,recordId,required:!!item.querySelector('.atsx-form-item-required'),disabled:!!el.disabled||!!el.closest('.atsx-select-disabled'),description:text(item.querySelector('.customResumeForm-fieldName-desc')),constraints:{},options:{state:['select','autocomplete'].includes(kind)?'requires-opening':'not-applicable',items:[]}};
    if(el.maxLength>0)f.constraints.maxLength=el.maxLength;
    if(kind==='month')f.constraints.format='YYYY-MM';if(kind==='year')f.constraints.format='YYYY';
    f.current=current(f);out.push(f);
   };
   for(const el of q('[role=combobox]',item).filter(visible))add(el,el.closest('.atsx-select-combobox')?'autocomplete':'select');
   for(const el of q('.atsx-date-picker-period-month-label',item).filter(visible))add(el,'month');
   for(const el of q('input,textarea',item).filter(visible)){
    if(el.closest('.atsx-select')||el.matches('.atsx-date-picker-period-hidden-input')||['checkbox','radio','file','hidden','password'].includes(el.type))continue;
    add(el,el.closest('.atsx-date-picker')?'year':'text');
   }
  }
  for(const item of q('.ud-formily-item').filter(visible)){
   const el=item.querySelector('.ud__select__selector__search__input'),label=item.getAttribute('data-form-field-i18n-name');
   if(el&&label==='是否上传作品'){const f={id:item.id,label,kind:'select',el,item,sectionId:'work-upload',recordId:'',required:false,disabled:false,customSelect:true,options:{state:'requires-opening',items:[]}};f.current=current(f);out.push(f);}
  }
  // The newer control has a different selected-value container.
  for(const f of out)if(f.customSelect)f.current=text(f.item.querySelector('.ud__select__selector__content'));
  return out;
 }
 const errors=()=>q('.atsx-form-explain,.ud-formily-item-feedback').filter(visible).map(text).filter(Boolean);
 async function write(f,value,ctx){
  ctx.check();
  if(f.kind==='text')setText(f.el,value);
  else if(f.customSelect){
   click(f.el);const option=await wait(()=>{const a=q('.ud__select__list__item',f.item).filter(e=>visible(e)&&text(e)===value);return a.length?one(a,'选项'):null;},ctx);click(option);outside();
  }else if(['select','autocomplete'].includes(f.kind)){
   click(f.el);if(f.kind==='autocomplete')setText(one(q('input',f.el),'搜索框'),value,false);
   const option=await wait(()=>{const a=q('[role=option]').filter(e=>visible(e)&&text(e)===value&&!e.className.includes('disabled'));return a.length?one(a,'下拉选项'):null;},ctx,10000);click(option);
   await wait(()=>f.el.getAttribute('aria-expanded')!=='true',ctx);outside();
  }else if(f.kind==='month'){
   const [year,month]=value.split('-');click(f.el);
   const popup=await wait(()=>q('.atsx-date-picker-period-month-panel').find(e=>visible(e)&&e.getAttribute('data-cy')===f.id+'Dropdown'),ctx);
   click(one(q('.atsx-date-picker-period-month-panel-list-item',popup).filter(e=>text(e)===year&&!e.className.includes('disabled')),'年份'));
   await wait(()=>text(f.el.querySelector('[data-cy=year]'))===year,ctx);
   click(one(q('.atsx-date-picker-period-month-panel-list-item',popup).filter(e=>text(e)===month&&!e.className.includes('disabled')),'月份'));outside();
  }else if(f.kind==='year'){
   click(f.el);const popup=await wait(()=>q('.atsx-date-picker-panel').find(visible),ctx);
   // Only choose a year actually offered by the rendered calendar.
   const offered=q('.atsx-date-picker-panel-body-cell-content',popup).filter(e=>text(e)===value&&!e.closest('[class*=disabled]'));
   click(one(offered,'可见年份'));
  }else throw Error('未支持的控件类型');
  await wait(()=>fields().find(x=>x.id===f.id)?.current===value,ctx,3500);
 }
 async function addRecord(sectionId,ctx){
  ctx.check();const root=one(q('.resumeEditForm-'+sectionId+'.createFormSection-repeatable').filter(visible),'经历区域');
  const before=q('.resumeEditForm-item',root).length,buttons=q('.formOperate-addBtn,.createFormSection-addBtn',root).filter(visible);
  if(!buttons.length)throw Error('没有添加按钮');click(buttons[buttons.length-1]);
  await wait(()=>q('.resumeEditForm-item',root).length===before+1,ctx);
 }
 window.JobFillAdapters=window.JobFillAdapters||{};
 window.JobFillAdapters.feishu={id:'feishu-xd',guard,page:()=>({adapter:'feishu-xd',url:location.href,title:document.title}),fields,sections,write,addRecord,errors,show,settle:async ctx=>{outside();await settle(errors,ctx);}};
})();
