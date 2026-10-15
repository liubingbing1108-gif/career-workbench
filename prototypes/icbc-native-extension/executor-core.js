/* Transport-independent execution protocol. This module contains no test answers. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.JobFillExecutorCore = api;
})(typeof globalThis === 'object' ? globalThis : this, () => {
  'use strict';
  const VERSION = '1.2.36';
  const clone = x => JSON.parse(JSON.stringify(x));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const empty = v => v === '' || (Array.isArray(v) && !v.length);
  function fail(code, message, details) { const e = new Error(message); e.code = code; e.details = details; throw e; }
  function keys(obj, allowed) {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) fail('INVALID_REQUEST', '请求必须为对象');
    for (const k of Object.keys(obj)) if (!allowed.includes(k)) fail('INVALID_REQUEST', '不支持参数：' + k);
  }
  function create(adapter) {
    const sessionId = 'session-' + (globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2));
    let serial = 0, snapshot, job = null, cancelled = false, navigating = false;
    const busy=()=>navigating||job?.status==='running';
    const requests = new Map();
    const page = () => JSON.stringify(adapter.page());
    const guard = () => { adapter.guard(); if (cancelled) fail('CANCELLED', '已停止后续动作，已发生的输入保留'); };
    const fresh = () => {
      adapter.guard(); const fields = adapter.fields();
      if (fields.some(f => !f.id) || new Set(fields.map(f => f.id)).size !== fields.length) fail('AMBIGUOUS_FIELD', '字段标识缺失或重复');
      return fields;
    };
    function capture() {
      const began=performance.now(), fields = fresh(), sections = adapter.sections(),attachments=adapter.attachments?.()||[];
      snapshot = { id: sessionId + ':' + (++serial), page: page(), fields, sections,attachments };
      return {
        schemaVersion: 1, executorVersion: VERSION, sessionId, snapshotId: snapshot.id,
        page: adapter.page(), capabilities: { fill: true, ensureRecords: !!adapter.addRecord, openSection: !!adapter.openSection, saveDraft: !!adapter.saveDraft&&(!adapter.canSaveDraft||adapter.canSaveDraft()), upload: !!adapter.uploadAttachment, submit: false },
        attachments:clone(attachments.map(({input,root,...item})=>item)),
        sections: clone(sections), fields: fields.map(f => ({ fieldId: f.id, label: f.label, kind: f.kind, sectionId: f.sectionId || '', recordId: f.recordId || '', required: !!f.required, disabled: !!f.disabled, description: f.description || '', context: f.context || {}, blockedReason: f.blockedReason || '', constraints: f.constraints || {}, options: f.options || { state: 'not-enumerated', items: [] }, currentValue: clone(f.current) })),
        scanElapsedMs:Math.round(performance.now()-began), coverage: 'currently-accessible-fields', coverageDetails: adapter.coverage?.() || {}, validation: adapter.errors()
      };
    }
    function requireSnapshot(id) {
      adapter.guard();
      if (!snapshot || id !== snapshot.id || snapshot.page !== page()) fail('STALE_SNAPSHOT', '页面或扫描已改变，请重新扫描');
      return snapshot;
    }
    function locate(saved, fields = fresh()) {
      const f = fields.find(x => x.id === saved.id);
      if (!f || f.el !== saved.el || f.kind !== saved.kind || f.label !== saved.label) fail('STALE_FIELD', '字段被重建或移动，请重新扫描：' + saved.label);
      return f;
    }
    function validateValue(f, value) {
      if(!['text','select','autocomplete','multiselect','radio','date','month','year','checkbox'].includes(f.kind))fail('UNSUPPORTED_CONTROL','控件类型尚未支持');
      if (f.kind === 'multiselect') {
        if (!Array.isArray(value) || !value.length || value.some(v => typeof v !== 'string' || !v) || new Set(value).size !== value.length) fail('INVALID_VALUE', '多选值须为不重复的字符串数组');
      } else if(f.kind==='checkbox'){if(typeof value!=='boolean')fail('INVALID_VALUE','复选值须为布尔值');} else if (typeof value !== 'string') fail('INVALID_VALUE', '字段值须为字符串');
      const c = f.constraints || {};
      if (f.required && empty(value)) fail('MISSING_VALUE', '必填字段不能清空：' + f.label);
      if (c.maxLength && typeof value === 'string' && value.length > c.maxLength) fail('VALUE_TOO_LONG', '超过字数限制：' + f.label);
      if(value===''&&!f.required){adapter.validate?.(f,value);return;}
      if (f.kind === 'month' && !/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) fail('INVALID_DATE', '月份须为 YYYY-MM');
      if (f.kind === 'year' && !/^\d{4}$/.test(value)) fail('INVALID_DATE', '年份须为 YYYY');
      if (f.kind === 'date' && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || (!Number.isFinite(Date.parse(value + 'T00:00:00Z')) || new Date(value + 'T00:00:00Z').toISOString().slice(0, 10) !== value))) fail('INVALID_DATE', '日期须为有效 YYYY-MM-DD');
      adapter.validate?.(f, value);
    }
    function checkAssignment(a, fields) {
      keys(a, ['fieldId', 'value', 'overwrite', 'sourceRef']);
      if (!['emptyOnly', 'ifUnchanged', undefined].includes(a.overwrite)) fail('INVALID_REQUEST', 'overwrite 无效');
      if (a.sourceRef !== undefined && typeof a.sourceRef !== 'string') fail('INVALID_REQUEST', 'sourceRef 须为字符串');
      const saved = snapshot.fields.find(f => f.id === a.fieldId);
      if (!saved) fail('UNKNOWN_FIELD', '只允许扫描返回的字段标识：' + a.fieldId);
      if (saved.disabled) fail('READ_ONLY_FIELD', '字段不可写：' + saved.label);
      const f = locate(saved, fields); validateValue(f, a.value);
      if (!same(f.current, saved.current)) fail('VALUE_CHANGED', '扫描后该字段已被修改：' + f.label);
      if (!same(f.current, a.value) && !empty(f.current) && a.overwrite !== 'ifUnchanged') fail('EXISTING_VALUE', '已有值默认保留：' + f.label);
      return { saved, assignment: clone(a) };
    }
    function validatePlan(plan) {
      keys(plan, ['schemaVersion', 'requestId', 'snapshotId', 'assignments']);
      if (plan.schemaVersion !== 1 || typeof plan.requestId !== 'string' || !plan.requestId || plan.requestId.length > 160) fail('INVALID_REQUEST', '需要 schemaVersion=1 和 requestId');
      requireSnapshot(plan.snapshotId);
      if (!Array.isArray(plan.assignments) || !plan.assignments.length || plan.assignments.length > 500) fail('INVALID_REQUEST', 'assignments 需要 1–500 项');
      if (new Set(plan.assignments.map(a => a.fieldId)).size !== plan.assignments.length) fail('DUPLICATE_FIELD', '同一计划不能重复写同一字段');
      const fields = fresh();
      const tasks = plan.assignments.map(a=>checkAssignment(a, fields));
      return tasks;
    }
    function cached(method, args) {
      const entry = requests.get(args?.requestId);
      if (!entry) return null;
      if (entry.signature !== JSON.stringify({ method, args })) fail('REQUEST_ID_REUSED', '同一个 requestId 不能用于不同指令');
      return { accepted: true, requestId: args.requestId, replayed: true, status: entry.job.status };
    }
    function start(method, args, work, preflightMs=0) {
      if (busy()) fail('BUSY', '当前页面已有执行任务');
      cancelled = false;
      job = { requestId: args.requestId, method, page: adapter.page(), status: 'running', elapsedMs: 0, preflightMs, results: [], submitted: false, saved: false, scope: 'current-page' };
      const currentJob = job, began = performance.now();
      requests.set(args.requestId, { signature: JSON.stringify({ method, args }), job });
      const context = { check: guard, progress: message => {currentJob.progress=message;adapter.show?.(message);} };
      void (async () => {
        try { await work(context, currentJob); guard(); currentJob.status = 'complete'; }
        catch (e) { currentJob.status = e.code === 'CANCELLED' ? 'cancelled' : 'failed'; currentJob.error = { code: e.code || 'ACTION_FAILED', message: e.message, details: e.details }; }
        finally {
          currentJob.elapsedMs = Math.round(performance.now() - began);
          currentJob.totalMs=currentJob.preflightMs+currentJob.elapsedMs;
          adapter.show?.((currentJob.status === 'complete' ? '完成' : '未完成') + '：' + method + '，' + currentJob.results.length + ' 项，' + (currentJob.elapsedMs / 1000).toFixed(2) + ' 秒。未提交申请。' + (currentJob.error ? currentJob.error.message : ''));
        }
      })();
      return { accepted: true, requestId: args.requestId, status: 'running' };
    }
    function execute(plan) {
      const hit = cached('execute', plan); if (hit) return hit;
      if (busy()) fail('BUSY', '当前页面已有执行任务');
      const preflightBegan=performance.now();const tasks = validatePlan(plan),preflightMs=Math.round(performance.now()-preflightBegan); // Entire plan checked before the first write.
      return start('execute', plan, async (ctx, j) => {
        const untouched = snapshot.fields.filter(f => !f.disabled && !tasks.some(t => t.saved.id === f.id));
        for (const { saved, assignment: a } of tasks) {
          ctx.check(); requireSnapshot(plan.snapshotId); const f = locate(saved);
          if (!same(f.current, saved.current)) fail('VALUE_CHANGED', '执行期间字段被修改：' + f.label);
          const began = performance.now();
          j.currentField={label:f.label,index:j.results.length+1,total:tasks.length,sectionId:f.sectionId||''};
          if (!same(f.current, a.value)||adapter.needsCommit?.(f))try{await adapter.write(f, a.value, ctx);}catch(e){e.message=f.label+'：'+e.message;e.details={fieldId:f.id,label:f.label};throw e;}
          const actual = locate(saved).current;
          if (!same(actual, a.value)) fail('READBACK_MISMATCH', '输入回读不一致：' + f.label, { fieldId: f.id });
          j.results.push({ fieldId: f.id, label: f.label, sourceRef: a.sourceRef, status: same(f.current, a.value) ? 'unchanged' : 'filled', expected: a.value, actual, elapsedMs: Math.round(performance.now() - began) });
        }
        await adapter.settle(ctx);
        const finalFields = fresh();
        for (const r of j.results) if (!same(finalFields.find(f => f.id === r.fieldId)?.current, r.expected)) fail('READBACK_MISMATCH', '整组回读失败：' + r.label);
        j.preserved = 0;
        for (const f of untouched) {if (!same(locate(f, finalFields).current, f.current)) fail('UNPLANNED_CHANGE', '未计划字段发生变化：' + f.label);j.preserved++;}
        j.validation = adapter.errors(); if (j.validation.length) fail('WEBSITE_VALIDATION', '网站存在可见校验提示', j.validation);
      },preflightMs);
    }
    function ensureRecords(args) {
      const hit = cached('ensureRecords', args); if (hit) return hit;
      keys(args, ['schemaVersion', 'requestId', 'snapshotId', 'sections']);
      if (args.schemaVersion !== 1 || typeof args.requestId !== 'string' || !args.requestId) fail('INVALID_REQUEST', '缺少版本或 requestId');
      if (!adapter.addRecord) fail('UNSUPPORTED', '本站尚未封装新增记录');
      const saved = requireSnapshot(args.snapshotId);
      if (!Array.isArray(args.sections) || !args.sections.length || args.sections.length > 20) fail('INVALID_REQUEST', 'sections 无效');
      if (new Set(args.sections.map(s => s.sectionId)).size !== args.sections.length) fail('INVALID_REQUEST', '分区重复');
      for (const s of args.sections) { keys(s, ['sectionId', 'count']); const actual = saved.sections.find(x => x.sectionId === s.sectionId); if (!actual?.canAdd || !Number.isInteger(s.count) || s.count < 0 || s.count > 20) fail('INVALID_REQUEST', '分区或数量不支持'); }
      return start('ensureRecords', args, async (ctx, j) => {
        for (const s of args.sections) {
          ctx.check(); const before = adapter.sections().find(x => x.sectionId === s.sectionId)?.count;
          if (before !== saved.sections.find(x => x.sectionId === s.sectionId).count) fail('STALE_SNAPSHOT', '经历数量已变化');
          for (let n = before; n < s.count; n++) {
            ctx.check(); await adapter.addRecord(s.sectionId, ctx);
            if (adapter.sections().find(x => x.sectionId === s.sectionId)?.count !== n + 1) fail('ADD_UNCERTAIN', '新增结果不明确，停止避免重复');
          }
          j.results.push({ sectionId: s.sectionId, before, after: Math.max(before, s.count), added: Math.max(0, s.count - before) });
        }
        for (const f of saved.fields.filter(f=>!f.disabled)) if (!same(locate(f).current, f.current)) fail('UNPLANNED_CHANGE', '新增时旧字段发生变化');
        j.preserved = saved.fields.length; j.snapshot = capture();
      });
    }
    function verify(args) {
      keys(args, ['requestId']); const previous = requests.get(args.requestId)?.job;
      if (!previous || previous.method !== 'execute' || previous.status !== 'complete') fail('NO_COMPLETED_PLAN', '没有该已完成的填写任务');
      adapter.guard(); if(JSON.stringify(previous.page)!==page())fail('STALE_PAGE','请返回执行时的同一页面/分区再核对'); const fields = fresh();
      const checks = previous.results.map(r => ({ fieldId: r.fieldId, passed: same(fields.find(f => f.id === r.fieldId)?.current, r.expected) }));
      return { complete: checks.every(c => c.passed) && !adapter.errors().length, checks, validation: adapter.errors(), scope: 'page-values-only' };
    }
    async function dispatch(method, args = {}) {
      try {
        if (method === 'status') return { ok: true, result: clone(args.requestId ? requests.get(args.requestId)?.job || null : job) };
        if (method === 'cancel') { cancelled = true; return { ok: true, result: { stopping: job?.status === 'running' } }; }
        if (method === 'scan') { if (busy()) fail('BUSY', '执行中不能重新生成扫描'); return { ok: true, result: capture() }; }
        if (method === 'readOptions'||method === 'readDateFormat') {
          keys(args,['snapshotId','fieldId']);if(busy())fail('BUSY','正在执行');requireSnapshot(args.snapshotId);
          const saved=snapshot.fields.find(f=>f.id===args.fieldId);if(!saved)fail('UNKNOWN_FIELD','未知字段');
          if(!adapter[method])fail('UNSUPPORTED','当前适配器未提供该项控件读取');
          const f=locate(saved);if(!same(f.current,saved.current))fail('VALUE_CHANGED','扫描后已修改');
          cancelled=false;navigating=true;try{return {ok:true,result:await adapter[method](f,{check:guard})};}finally{navigating=false;}
        }
        if (method === 'execute') return { ok: true, result: execute(args) };
        if (method === 'ensureRecords') return { ok: true, result: ensureRecords(args) };
        if (method === 'validate') { const tasks = validatePlan(args); return { ok: true, result: { valid: true, count: tasks.length, writesPerformed: 0 } }; }
        if (method === 'verify') return { ok: true, result: verify(args) };
        if (method === 'openSection') {
          keys(args, ['sectionId']); if (busy()) fail('BUSY', '正在执行');
          if (!adapter.openSection) fail('UNSUPPORTED', '本站不需要切换分区');
          cancelled = false; navigating=true;try{await adapter.openSection(args.sectionId, { check: guard }); snapshot = null; return { ok: true, result: capture() };}finally{navigating=false;}
        }
        if(method==='saveDraft'){
          const hit=cached('saveDraft',args);if(hit)return {ok:true,result:hit};
          keys(args,['schemaVersion','requestId','snapshotId']);
          if(args.schemaVersion!==1||typeof args.requestId!=='string'||!args.requestId)fail('INVALID_REQUEST','缺少版本或 requestId');
          const s=requireSnapshot(args.snapshotId);if(!adapter.saveDraft)fail('UNSUPPORTED','本站没有已验证的草稿保存动作');
          for(const f of s.fields.filter(f=>!f.disabled))if(!same(locate(f).current,f.current))fail('VALUE_CHANGED','扫描后内容已改变');
          return {ok:true,result:start('saveDraft',args,async(ctx,j)=>{await adapter.saveDraft(ctx);j.saved=true;j.results.push({status:'website-save-success-feedback'});})};
        }
        if(method==='uploadAttachment'){
          const hit=cached(method,args);if(hit)return {ok:true,result:hit};
          keys(args,['schemaVersion','requestId','snapshotId','attachmentId','fileName','mimeType','base64','sourceRef']);
          if(args.schemaVersion!==1||typeof args.requestId!=='string'||!args.requestId)fail('INVALID_REQUEST','缺少版本或 requestId');
          requireSnapshot(args.snapshotId);if(!adapter.uploadAttachment||!adapter.attachments)fail('UNSUPPORTED','本站没有附件驱动');
          if(typeof args.fileName!=='string'||!args.fileName||args.fileName.length>300||/[\/\\\x00]/.test(args.fileName)||typeof args.mimeType!=='string'||args.mimeType.length>150||typeof args.base64!=='string'||!args.base64.length||args.base64.length>Math.ceil(50*1024*1024/3)*4||!/^[A-Za-z0-9+/]+={0,2}$/.test(args.base64)||args.base64.length%4!==0)fail('INVALID_REQUEST','附件名称或原件数据无效');
          const found=snapshot.attachments.filter(a=>a.attachmentId===args.attachmentId);if(found.length!==1)fail('UNKNOWN_FIELD','没有唯一对应的上传入口');
          const before=found[0];
          return {ok:true,result:start(method,args,async(ctx,j)=>{ctx.check();const current=adapter.attachments().find(a=>a.attachmentId===before.attachmentId);if(!current||current.input!==before.input||!same(current.fileNames,before.fileNames))fail('VALUE_CHANGED','扫描后附件已被修改');const result=await adapter.uploadAttachment(current,args,ctx);j.results.push(result);})};
        }
        // No arbitrary click, script, selector, navigation or final-submit method.
        fail('UNSUPPORTED_METHOD', '不支持此动作：' + method);
      } catch (e) { return { ok: false, error: { code: e.code || 'ACTION_FAILED', message: e.message, details: e.details } }; }
    }
    return { version: VERSION, dispatch };
  }
  return { VERSION, create };
});
