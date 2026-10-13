/* Same-origin host contract. This module never changes a job or performs an API write. */
(function (root, factory) {
  const contract = factory();
  if (typeof module === 'object' && module.exports) module.exports = contract;
  else {
    root.ManagementIntegration = contract;
    // Run before body rendering to avoid a duplicate site header flashing in the iframe.
    if (contract.isEmbedded(root.location.search)) document.documentElement.classList.add('embedded');
  }
})(typeof window === 'undefined' ? globalThis : window, function () {
  function isEmbedded(search) { return new URLSearchParams(search).get('embedded') === '1'; }
  function apiPath(path, search) {
    if (!path.startsWith('/api/')) throw new Error('管理 API 路径无效');
    return isEmbedded(search) ? '/management' + path : path;
  }
  function preparePayload(job, readOnly = false, sourceId = null) {
    if (readOnly) throw new Error('请先确认录入管理表格，再开始投递');
    const company = String(job.company || '').trim();
    const title = String(job.role || '').trim();
    let url;
    if(job.source_url||job.url){try { url = new URL(job.source_url||job.url); } catch { throw new Error('请先补齐有效的招聘链接'); }
    if (!['http:','https:'].includes(url.protocol) || !url.hostname) throw new Error('请先补齐有效的来源链接');}
    if (!company || !title || job.needs_review || (job.role_summary && /[、；;\n]/.test(title))) throw new Error('请先补齐或拆分为一个具体岗位');
    return {type: 'workbench:prepare', job: {
      id: job.id, company, title, source_url: url?.href || '', official_url: job.official_url||'', apply_url: job.official_url_status==='verified'?(job.official_url||''):'',
      application_status: job.application_status || '未投递', recruitment_stage: job.recruitment_stage || '',
      preference_order: job.preference_order || '', requires_preference: Boolean(job.requires_preference),
      location: job.location || '', campaign: job.campaign || '',
      source_kind: job.source_kind || '', source_table: job.source_table || '', source_record_id: job.source_record_id || '',
      readonly: false
    }};
  }
  function canPrepare(job) { try { preparePayload(job); return true; } catch { return false; } }
  function listStats(rows, readOnly, candidatePreview = false) {
    const pending = rows.filter(job => job.application_status === '未投递').length;
    return [['投递事项', rows.length], ['计划投递', pending], ['已投递', rows.length - pending]];
  }
  function postPrepare(job, readOnly, host, sourceId = null) {
    const payload = preparePayload(job, readOnly, sourceId);
    if (host.parent === host) throw new Error('请在统一网站的投递管理 Tab 中准备投递');
    // A same-origin target prevents delivery to an unrelated embedding site.
    host.parent.postMessage(payload, host.location.origin);
    return payload;
  }
  function postDeleted(jobId, host) {
    if (host.parent !== host) host.parent.postMessage({type: 'workbench:deleted', job_id: jobId}, host.location.origin);
  }
  return {isEmbedded, apiPath, preparePayload, canPrepare, listStats, postPrepare, postDeleted};
});
