/* Generic DOM scanner and reusable widget drivers. No company URLs or resume answers. */
(() => {
  'use strict';
  const D = window.JobFillDOM;
  const {text, visible, one, click, setTextCommitted:setText, wait, show} = D;
  const originPage = location.href;
  const ids = new WeakMap(); let nextId = 0;
  const dateKinds = new WeakMap();
  const idFor = (el, prefix = 'field') => {if (!ids.has(el)) ids.set(el, prefix + '-' + (++nextId)); return ids.get(el);};
  let cachedRoots=[document];
  const refreshRoots = () => {const out = [document]; for (let i=0; i<out.length; i++) for (const e of out[i].querySelectorAll('*')) if (e.shadowRoot) out.push(e.shadowRoot); cachedRoots=out;return out;};
  const roots=()=>cachedRoots;
  const all = (s, root) => root ? [...root.querySelectorAll(s)] : roots().flatMap(r=>[...r.querySelectorAll(s)]);
  const containerSelector = '.ant-form-item,.el-form-item,.atsx-form-item,.ud-formily-item,[class*="apply-field-"],[data-field-name],.form-group,.form-item,fieldset';
  const blockSelector = '[class*="apply-block-"],.createFormSection-repeatable,fieldset,.form-cell';
  const rowSelector = '[class*="apply-fields-"],.resumeEditForm-item,.ux-standard-form,.form-cell-inner';
  function phoenixBlocks(){return all('[id$="_addButton"]').map(add=>{const titleId=add.id.slice(0,-10);let p=add.parentElement;while(p&&p!==document.body){if([...p.children].some(c=>c.id===titleId&&!c.querySelector('input,textarea')))return p;p=p.parentElement;}return null;}).filter(Boolean);}
  const blockFor=el=>el.closest(blockSelector)||phoenixBlocks().find(b=>b.contains(el));
  function guard() {
    if (location.protocol !== 'https:' || location.href !== originPage) throw Error('网页已切换，请重新扫描');
    if (all('input[type=password]').some(visible)) throw Error('登录或密码页面由本人处理');
  }
  function sectionLabel(root) {
    const title = root.querySelector('[class*="blockTitle-"],.createFormSection-text,legend,h2,h3,[role=heading],.tit-wrap .tit p,.tit-wrap .tit');
    return (text(title)||text([...root.children].find(c=>c.id&&!c.querySelector('input,textarea')))).replace(/[\ue000-\uf8ff]/g,'').replace(/(添加|新增)$/,'').trim();
  }
  function blocks() {return [...new Set([...all(blockSelector).filter(visible).filter(e=>!e.parentElement?.closest(blockSelector)),...phoenixBlocks()])];}
  function addButton(root) {
    const a = all('button,[role=button],.formOperate-addBtn,.createFormSection-addBtn,.add-more-btn,[id$="_addButton"]',root).filter(e=>visible(e)&&!e.disabled&&/^(添加|新增)(.{0,80})?$/.test(text(e).replace(/[\ue000-\uf8ff]/g,'').trim()));
    return a.length===1 ? a[0] : null;
  }
  function sections() {return blocks().map(b=>({sectionId:idFor(b,'section'),label:sectionLabel(b),description:text(b.querySelector('.tit-wrap,.createFormSection-text,legend,[class*="blockTitle-"]')).slice(0,3000),count:all(rowSelector,b).filter(visible).length,canAdd:!!addButton(b)&&! /声明|隐私|协议|照片|附件|家庭/.test(sectionLabel(b))&&(all(rowSelector,b).length>0||b.matches('.form-cell'))}));}
  function labelFor(el, item) {
    const aria = el.getAttribute('aria-label'); if (aria) return aria;
    const labelled = el.getAttribute('aria-labelledby');
    if (labelled) {const names=labelled.split(/\s+/).map(id=>text(el.getRootNode().getElementById?.(id))).filter(Boolean); if(names.length)return names.join(' ');}
    const heading=item?.querySelector('.ant-form-item-label,.el-form-item__label,.atsx-form-item-label,.form-item__text,[class^="title-"],legend,[data-field-label]');
    if(text(heading))return text(heading);
    const explicit = el.labels && [...el.labels].map(n=>{const c=n.cloneNode(true);c.querySelectorAll('input,select,textarea,[role=combobox]').forEach(x=>x.remove());return text(c);}).filter(Boolean).join(' ');
    if (explicit && explicit.length<100 && !/[\ue000-\uf8ff]/.test(explicit)) return explicit;
    return text(heading) || item?.getAttribute('data-field-name') || el.getAttribute('placeholder') || el.getAttribute('name') || '';
  }
  const widget = el => {
    const autocomplete=el.closest('.phoenix-auto-complete-container');if(autocomplete)return {driver:'phoenix-autocomplete',root:autocomplete};
    const sugar=el.closest('[class*="sd-Select-container"]');
    if(sugar){
      const item=el.closest('[class*="apply-field-"]');
      if(item?.querySelector('.date_info,.month-range-select')) {
        const selects=all('[class*="sd-Select-container"]',item);
        if(selects.length===2||selects.length===4){const n=selects.indexOf(sugar),parts=selects.slice(Math.floor(n/2)*2,Math.floor(n/2)*2+2);return {driver:'sugar-month',root:parts[0],parts,suffix:selects.length===4?(n<2?'（开始）':'（结束）'):''};}
      }
      return {driver:'sugar',root:sugar};
    }
    const phoenix=el.closest('.phoenix-select'); if(phoenix)return {driver:[...phoenix.querySelectorAll('use')].some(e=>(e.getAttribute('xlink:href')||e.getAttribute('href')||'').includes('date_time_picker'))?'phoenix-calendar':'phoenix',root:phoenix};
    const calendar=el.closest('.ant-calendar-picker');if(calendar&&!calendar.querySelector('.ant-calendar-range-picker-input'))return {driver:'ant-date',root:calendar};
    const ant=el.closest('.ant-select,.atsx-select'); if(ant)return {driver:'ant',root:ant};
    const element=el.closest('.el-select'); if(element)return {driver:'element',root:element};
    if(el.matches('[role=combobox]'))return {driver:'aria',root:el};
    return null;
  };
  function current(f) {
    if(f.driver==='ant-date')return f.root.querySelector('input')?.value||'';
    if(f.driver==='sugar-month'){const v=f.parts.map(e=>text(e.querySelector('[class*="sd-Input-display-value-"]')));return v.every(Boolean)?v[0]+'-'+v[1].padStart(2,'0'):'';}
    if(f.driver==='native-select') return f.el.multiple ? [...f.el.selectedOptions].map(text) : text(f.el.selectedOptions[0]);
    if(f.driver==='radio') return text(f.group.find(e=>e.checked)?.closest('label')) || f.group.find(e=>e.checked)?.value || '';
    if(f.driver==='checkbox')return f.el.checked;
    if(f.driver==='contenteditable')return f.el.innerText;
    if(f.driver==='sugar')return text(f.root.querySelector('[class*="sd-Input-display-value-"]'));
    if(f.driver==='ant') {
      if(f.kind==='multiselect')return all('.ant-select-selection__choice__content,.ant-select-selection-item-content',f.root).map(text);
      return text(f.root.querySelector('.ant-select-selection-selected-value,.ant-select-selection-item,.atsx-select-selection-selected-value'));
    }
    if(['phoenix','phoenix-calendar','phoenix-autocomplete'].includes(f.driver))return f.root.querySelector('input')?.value||text(f.root.querySelector('.phoenix-select__tipEle'));
    if(f.driver==='element')return f.root.querySelector('input')?.value||text(f.root.querySelector('.el-select__selected-item:not(.el-select__placeholder)'));
    if(f.driver==='aria')return f.el.value||text(f.el.querySelector('[aria-selected=true]'))||text(f.el);
    return f.el.value || '';
  }
  function fields() {
    refreshRoots();guard(); const out=[], seen=new Set();
    for(const el of all('input,textarea,select,[contenteditable=true],[role=combobox]')) {
      if(!visible(el)||el.closest('#jobfill-executor-report,#jobfill-executor-progress,.ant-calendar,.ant-select-dropdown,.phoenix-selectList,.phoenix-calendar,.constant-main-selector-container,.common-unmodeled-layer')||['hidden','submit','button','reset','image'].includes(el.type))continue;
      const w=widget(el), canonical=w?.root||el;
      if(seen.has(canonical))continue; seen.add(canonical);
      const item=el.closest(containerSelector)||el.parentElement;
      let label=labelFor(el,item),driver='native-text',kind='text',group;
      if(w){driver=w.driver;kind=/multiple/.test(w.root.className)||w.root.getAttribute('aria-multiselectable')==='true'?'multiselect':'select';}
      if(w?.driver==='unsupported'){kind='unsupported';}
      else if(w?.driver==='phoenix-autocomplete'){kind='autocomplete';}
      else if(w?.driver==='phoenix-calendar'){kind=dateKinds.get(w.root)||(/^\d{4}-\d{2}-\d{2}$/.test(el.value)?'date':/^\d{4}-\d{2}$/.test(el.value)?'month':'unsupported');}
      else if(w?.driver==='ant-date'){kind=/^\d{4}-\d{2}$/.test(el.value)||/年月|月份/.test(el.placeholder||'')?'month':'date';}
      else if(w?.driver==='sugar-month'){kind='month';label+=w.suffix;}
      else if(el.tagName==='SELECT'){driver='native-select';kind=el.multiple?'multiselect':'select';}
      else if(el.type==='radio'){
        driver='radio';kind='radio';group=all('input[type=radio]',el.form||item).filter(e=>e.name===el.name&&visible(e));
        if(!el.name)group=all('input[type=radio]',item).filter(visible); if(group.some(e=>seen.has(e)&&e!==el))continue;group.forEach(e=>seen.add(e));
        label=text(item?.querySelector('legend,.ant-form-item-label,.el-form-item__label'))||label;
      }else if(el.type==='checkbox'){driver='checkbox';kind='checkbox';const option=text(el.closest('label,.phoenix-checkbox'));if(option&&option!==label)label+='（'+option+'）';}
      else if(el.isContentEditable){driver='contenteditable';kind='text';}
      else if(['date','month'].includes(el.type))kind=el.type;
      else if(el.readOnly){driver='unsupported';kind='unsupported';}
      const block=blockFor(el),row=el.closest(rowSelector);
      const controls=item?all('input,textarea,select',item).filter(visible):[];
      const componentIndex=controls.indexOf(el);
      const description=[el.getAttribute('placeholder'),text(item?.querySelector('.ant-form-extra,.el-form-item__error,[class*=description]'))].filter(Boolean).join('；');
      const sensitive=/密码|验证码|证件|身份证|护照|隐私|协议|承诺|声明|银行账号|账户密码|上传|照片|附件|搜索/.test(label+' '+(el.placeholder||''))||['file','password','search'].includes(el.type);
      const disabled=!!el.disabled||el.getAttribute('aria-disabled')==='true'||!!el.closest('.ant-select-disabled,.el-select.is-disabled,.phoenix-select--disabled,[class*="sd-Input-disabled"]')||sensitive||driver==='unsupported'||!label;
      const constraints={};if(el.maxLength>0)constraints.maxLength=el.maxLength;if(['date','month'].includes(kind))constraints.format=kind==='date'?'YYYY-MM-DD':'YYYY-MM';
      const f={id:idFor(canonical),label:label||'未命名控件',el:canonical,input:el,root:canonical,parts:w?.parts,item,driver,group,kind,sectionId:block?idFor(block,'section'):'page',recordId:row?idFor(row,'row'):'',required:!!el.required||el.getAttribute('aria-required')==='true'||!!item?.querySelector('.ant-form-item-required,.el-form-item.is-required,[class*=required],.form-item__required'),disabled,description,constraints,
       context:{section: block?sectionLabel(block):'',componentIndex,placeholder:el.getAttribute('placeholder')||'',tag:el.tagName,type:el.type||'',driver},
       blockedReason:sensitive?'需本人处理的身份/认证/协议/附件或非简历搜索字段':driver==='phoenix-calendar'&&kind==='unsupported'?'日期选择器尚未打开，系统需要重新识别后填写':driver==='unsupported'?'自定义日期或只读控件尚未识别':!label?'缺少可靠标签':disabled?'网页标记不可编辑':'',
       options:{state:'requires-opening',items:[]}};
      if(!w)f.el=el;
      if(driver==='native-select')f.options={state:'enumerated',items:[...el.options].filter(o=>!o.disabled).map(text)};
      else if(driver==='radio')f.options={state:'enumerated',items:group.filter(e=>!e.disabled).map(e=>text(e.closest('label'))||e.value)};
      else if(!['select','multiselect'].includes(kind))f.options={state:'not-applicable',items:[]};
      f.current=current(f);out.push(f);
    }
    return out;
  }
  const optionSelectors='[role=option],.ant-select-dropdown-menu-item,.ant-select-item-option,.atsx-select-dropdown-menu-item,.el-select-dropdown__item,.phoenix-selectList__listItem,[class*="sd-Menu-content-item-"]';
  function optionsFor(f) {
    const owner=f.input.getAttribute('aria-controls')||f.input.getAttribute('aria-owns')||f.root.getAttribute('aria-controls');
    const popup=owner?f.input.getRootNode().getElementById?.(owner):null;
    const candidates=all(optionSelectors,popup||undefined).filter(e=>visible(e)&&e.getAttribute('aria-disabled')!=='true'&&!/disabled/i.test(e.className));
    return candidates.filter(e=>!candidates.some(other=>other!==e&&e.contains(other)));
  }
  const constantPanel=()=>all('.constant-main-selector-container').find(visible);
  async function closeMenu(f,ctx) {
    const panel=constantPanel();if(panel){click(one(all('.phoenix-button__content',panel).filter(e=>text(e)==='取消'),'关闭选择窗口'));await wait(()=>!visible(panel),ctx);return;}
    if(f.root.contains(document.activeElement))document.activeElement.blur();
    const target=f.root.querySelector('input')||f.input;target.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',keyCode:27,which:27,bubbles:true}));target.dispatchEvent(new KeyboardEvent('keyup',{key:'Escape',code:'Escape',keyCode:27,which:27,bubbles:true}));
    if(optionsFor(f).length){const title=f.item?.querySelector('.form-item__text,.ant-form-item-label,.el-form-item__label,[class^="title-"]')||all('h1,h2,legend,[class*="blockTitle-"]').find(visible);click(title||document.body);}
    await wait(()=>!optionsFor(f).length,ctx,2000);
  }
  async function readOptions(f,ctx) {
    if(f.options.state==='enumerated')return f.options;
    if(!['select','multiselect'].includes(f.kind)||f.disabled)throw Error('这个控件不提供候选读取');
    const before=JSON.stringify(current(f));click(f.input);
    try {await wait(()=>optionsFor(f).length||constantPanel(),ctx);if(constantPanel())return {state:'requires-search',items:[],complete:false};return {state:'visible-options',items:optionsFor(f).map(text),complete:false};}
    finally {await closeMenu(f,ctx);if(JSON.stringify(current(f))!==before)throw Error('读取选项意外改变字段');}
  }
  async function calendarPanel(f,ctx){
    const existing=all('.phoenix-calendar').filter(visible);
    if(existing.length)click(f.item?.querySelector('.form-item__text')||document.body);
    click(f.input);return await wait(()=>{const p=all('.phoenix-calendar').filter(visible);return p.length?one(p,'日期弹层'):null;},ctx);
  }
  function calendarKind(panel){
    if(all('.phoenix-calendar-date-panel',panel).some(visible))return 'date';
    if(all('.phoenix-calendar-month-panel',panel).some(visible))return 'month';
    throw Error('未识别的日期精度，停止避免填错');
  }
  async function readDateFormat(f,ctx){
    if(f.driver!=='phoenix-calendar'||f.disabled)throw Error('该控件不支持日期精度读取');
    const before=current(f),panel=await calendarPanel(f,ctx);
    const kind=calendarKind(panel);dateKinds.set(f.root,kind);
    click(f.item?.querySelector('.form-item__text')||document.body);
    await wait(()=>!visible(panel),ctx);
    if(current(f)!==before)throw Error('读取日期精度意外改变字段');
    return {kind,format:kind==='date'?'YYYY-MM-DD':'YYYY-MM',writesPerformed:0};
  }
  async function writePhoenixDate(f,expected,ctx){
    const panel=await calendarPanel(f,ctx),kind=calendarKind(panel);
    if(kind!==f.kind)throw Error('日期精度已变化，请重新读取');
    if(kind==='date'){
      const input=one(all('.phoenix-calendar-input',panel).filter(visible),'日期输入框');
      await setText(input,expected,false);
      input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
    }else{
      const [year,month]=expected.split('-').map(Number);
      const selectedYear=()=>Number(text(one(all('.phoenix-calendar-month-panel-year-select-content',panel).filter(visible),'年月中的年份')));
      let actual=selectedYear();if(!Number.isInteger(actual)||Math.abs(year-actual)>100)throw Error('年月年份跨度超出可执行范围');
      while(actual!==year){
        ctx.check();const before=actual;
        click(one(all(year>actual?'.phoenix-calendar-month-panel-next-year-btn':'.phoenix-calendar-month-panel-prev-year-btn',panel).filter(visible),'年月年份切换'));
        actual=await wait(()=>{const next=selectedYear();return next!==before?next:null;},ctx);
      }
      const choices=all('.phoenix-calendar-month-panel-month',panel).filter(e=>visible(e)&&text(e)===month+'月'&&!/disabled/.test(e.parentElement.className));
      click(one(choices,'指定月份'));
    }
    await wait(()=>!visible(panel)&&current(f)===expected,ctx,3000);
  }
  async function write(f,expected,ctx) {
    ctx.check(); if(f.disabled)throw Error(f.blockedReason||'字段不可写');
    if(f.driver==='phoenix-autocomplete'){
      if(optionsFor(f).length)await closeMenu(f,ctx);
      await setText(f.input,expected,false);
      const exact=await wait(()=>{const found=optionsFor(f).filter(e=>text(e)===expected);return found.length?found:null;},ctx,8000);
      click(one(exact,'精确搜索候选'));await closeMenu(f,ctx);
    }else if(f.driver==='phoenix-calendar')await writePhoenixDate(f,expected,ctx);
    else if(f.driver==='ant-date'){
      if(expected===''){click(one(all('.ant-calendar-picker-clear',f.root),'日历清除按钮'));await wait(()=>current(f)==='',ctx);return;}
      if(f.kind!=='date')throw Error('此版本尚未验证 Ant 月份弹层');
      click(f.input);const panel=await wait(()=>all('.ant-calendar').find(visible),ctx);
      const input=one(all('.ant-calendar-input',panel).filter(visible),'日历文本输入');
      await setText(input,expected,false);const [y,m,d]=expected.split('-').map(Number);
      const cell=await wait(()=>all('td[title]',panel).find(e=>e.title===y+'年'+m+'月'+d+'日'&&!/disabled/.test(e.className)),ctx);
      const date=cell.querySelector('.ant-calendar-date');if(date?.getAttribute('aria-disabled')==='true')throw Error('日期不可选择');
      click(date||cell);await wait(()=>!visible(panel),ctx);
    }else if(f.driver==='sugar-month'){
      const values=expected.split('-');
      for(let i=0;i<2;i++){const root=f.parts[i],input=root.querySelector('input');const part={...f,root,el:root,input,driver:'sugar',kind:'select'};if(current(part)!==String(Number(values[i])))await write(part,String(Number(values[i])),ctx);}
    }else if(f.driver==='native-select'){
      const wanted=Array.isArray(expected)?expected:[expected];
      const chosen=wanted.map(v=>one([...f.el.options].filter(o=>!o.disabled&&text(o)===v),'下拉选项'));
      for(const o of f.el.options)o.selected=chosen.includes(o);
      f.el.dispatchEvent(new Event('input',{bubbles:true}));f.el.dispatchEvent(new Event('change',{bubbles:true}));f.el.blur();
    }else if(f.driver==='checkbox') {if(f.el.checked!==expected)click(f.el);}
    else if(f.driver==='radio'){click(one(f.group.filter(e=>!e.disabled&&(text(e.closest('label'))||e.value)===expected),'单选选项'));}
    else if(f.driver==='contenteditable'){
      f.el.focus();f.el.textContent=expected;f.el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:expected}));f.el.dispatchEvent(new Event('change',{bubbles:true}));f.el.blur();
    }else if(['sugar','ant','element','aria','phoenix'].includes(f.driver)){
      if(expected===''&&f.driver==='ant'){click(one(all('.ant-select-selection__clear,.ant-select-clear',f.root),'下拉清除按钮'));await wait(()=>current(f)==='',ctx);return;}
      if(f.kind==='multiselect')throw Error('自定义多选需要对应选项状态驱动，当前不猜测追加');
      click(f.input);
      await wait(()=>optionsFor(f).length||constantPanel(),ctx);
      const panel=constantPanel();
      if(panel){
        // A searchable hierarchy has its own radio and confirmation controls.
        // Search only the already-confirmed value; never pick a similar category.
        let step='搜索分类';
        try{
          const input=one(all('input[placeholder="搜索"]',panel).filter(visible),'专业类别搜索框');
          await setText(input,expected,false);
          const choice=await wait(()=>{const found=all('.list-item-container',panel).filter(e=>visible(e)&&text(e.querySelector('.item-text-label'))===expected);return found.length===1?found[0]:null;},ctx,8000);
          step='选中分类';const radio=choice.querySelector('.icon-container');if(!radio)throw Error('没有可选择的相同类别');const target=radio.querySelector('svg')||radio;target.dispatchEvent(new MouseEvent('click',{bubbles:true,composed:true,button:0}));
          await wait(()=>all('.select-data-container .select-text-label',panel).some(e=>text(e)===expected),ctx);
          step='确认分类';click(one(all('.phoenix-button__content',panel).filter(e=>text(e)==='确定'),'确认专业类别'));
          await wait(()=>!visible(panel)&&current(f)===expected,ctx);return;
        }catch(e){throw Error(step+'未完成：'+e.message);}finally{if(visible(panel))await closeMenu(f,ctx);}
      }
      let opts=optionsFor(f);
      let exact=opts.filter(e=>text(e)===expected);
      if(!exact.length && f.input.tagName==='INPUT'&&!f.input.readOnly){await setText(f.input,expected,false);exact=await wait(()=>{const v=optionsFor(f).filter(e=>text(e)===expected);return v.length?v:null;},ctx,8000);}
      click(one(exact,'精确下拉选项'));await closeMenu(f,ctx);
    }else if(f.driver==='native-text')await setText(f.el,expected);
    else throw Error('尚未支持的控件操作');
    await wait(()=>JSON.stringify(current(f))===JSON.stringify(expected),ctx,3000);
    if(f.input.validity&&!f.input.validity.valid&&f.driver==='native-text')throw Error('浏览器原生校验未通过：'+f.input.validationMessage);
  }
  function validate(f,value){
    if(f.kind==='multiselect'&&f.driver!=='native-select')throw Error('自定义多选尚未完成驱动验证');
    if(f.driver==='ant-date'&&f.kind!=='date')throw Error('Ant 月份弹层尚未验证');
    if(value===''&&!f.required){if(['native-text','contenteditable','ant','ant-date'].includes(f.driver))return;if(f.driver!=='native-select')throw Error('该控件尚未支持清空');}
    if(f.options.state==='enumerated')for(const v of(Array.isArray(value)?value:[value]))if(!f.options.items.includes(v))throw Error('不在已枚举选项中：'+v);
  }
  function errors(){return all('.ant-form-explain,.ant-form-item-explain-error,.el-form-item__error,.atsx-form-explain,.ud-formily-item-feedback,[class*="errorMessage"],[class*="error-message"]').filter(visible).map(text).filter(Boolean);}
  async function addRecord(sectionId,ctx){
    ctx.check();const b=one(blocks().filter(e=>idFor(e,'section')===sectionId),'新增分区');
    const before=all(rowSelector,b).length;const button=addButton(b);if(!button)throw Error('没有唯一明确的新增按钮');click(button);
    await wait(()=>all(rowSelector,b).length===before+1,ctx);
  }
  function attachments(){return all('.file-uploader__wrapper').filter(visible).map(root=>{const item=root.closest(containerSelector);return {attachmentId:idFor(root,'attachment'),label:text(item?.querySelector('.form-item__text')),required:!!item?.querySelector('.form-item__required'),fileNames:all('.file-uploader__list-view > *',root).map(text).filter(Boolean),input:root.querySelector('input[type=file]')};}).filter(a=>a.input&&a.label);}
  async function uploadAttachment(attachment,file,ctx){
    const present=attachment.fileNames.length===1&&attachment.fileNames[0]===file.fileName;
    if(!present){
      const raw=Uint8Array.from(atob(file.base64),c=>c.charCodeAt(0));
      const transfer=new DataTransfer();transfer.items.add(new File([raw],file.fileName,{type:file.mimeType}));
      attachment.input.files=transfer.files;attachment.input.dispatchEvent(new Event('change',{bubbles:true}));
    }
    // A matching filename may still be uploading, including on retries. The
    // observed Phoenix PDF card gains preview/download/delete only when ready.
    let stable=null,previous='';
    try{await wait(()=>{
      const root=attachment.input.closest('.file-uploader__wrapper'),row=root?.querySelector('.file-uploader__list-view');
      const names=root?all('.file-uploader__list-view > *',root).map(text).filter(Boolean):[];
      const markup=row?.innerHTML||'';
      if(names.length!==1||names[0]!==file.fileName||!markup||row.querySelectorAll('svg').length<3||row.querySelector('[role=progressbar],.phoenix-loading,.phoenix-spin,[class*=uploading]')){stable=null;previous='';return false;}
      if(stable===null||markup!==previous){previous=markup;stable=performance.now();}
      return performance.now()-stable>=700;
    },ctx,30000);}catch(e){ctx.check();throw Error('简历附件尚未完成上传，请等待或在官网重试；未将文件名出现视为上传成功。');}
    if(errors().length)throw Error('官网附件上传存在校验提示');
    return {status:present?'attachment-present':'attachment-uploaded',fileName:file.fileName};
  }
  function draftButton(){const found=all('button').filter(e=>visible(e)&&!e.disabled&&text(e)==='暂存');return all('.form-item--phoenix').length&&found.length===1?found[0]:null;}
  async function saveDraft(ctx){
    const button=draftButton();if(!button)throw Error('没有唯一明确的草稿暂存按钮');
    let receipt='',feedback='';const collect=node=>{const el=node.nodeType===3?node.parentElement:node;if(!el||!visible(el))return;const value=text(el);if(value.length<=100&&/保存|暂存|成功|失败|错误/.test(value))feedback=value;if(value.length<=100&&/^(?:简历)?(?:保存|暂存)成功(?:[，,]请到[「“]?投递记录[」”]?中查看)?(?:[。！!]|\s)*$/.test(value))receipt=value;};
    const observer=new MutationObserver(records=>records.forEach(r=>{collect(r.target);r.addedNodes.forEach(collect);}));
    observer.observe(document.body,{childList:true,subtree:true,characterData:true});
    try{click(button);try{await wait(()=>receipt,ctx,10000);}catch(e){throw Error(e.message+(feedback?'；官网反馈：'+feedback:''));}if(errors().length)throw Error('官网存在校验提示');return receipt;}
    finally{observer.disconnect();}
  }
  window.JobFillAdapters=window.JobFillAdapters||{};
  window.JobFillAdapters.generic={id:'generic-dom',guard,page:()=>({adapter:'generic-dom',url:location.href,title:document.title}),fields,sections,write,validate,readOptions,readDateFormat,addRecord,errors,show,
    needsCommit:f=>f.driver==='phoenix-autocomplete'&&f.root.contains(document.activeElement)&&optionsFor(f).length>0,attachments,uploadAttachment,canSaveDraft:()=>!!draftButton(),saveDraft,
    coverage:()=>({frames:all('iframe').length,openShadowRoots:roots().length-1,frameContentsScanned:false,clientRevision:window.JobFillClientRevision||'',nativeTextBridgeReady:D.nativeTextBridgeReady}),
    settle:async ctx=>{document.activeElement?.blur();await D.settle(errors,ctx);}};
})();
