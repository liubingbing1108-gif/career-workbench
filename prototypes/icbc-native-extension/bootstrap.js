(() => {
 'use strict';
 const core=window.JobFillExecutorCore;
 if(window.JobFillExecutor?.version===core.VERSION&&window.JobFillExecutorScope===location.href)return;
 let adapter=window.JobFillAdapters.generic;
 if(location.hostname==='job.icbc.com.cn'&&document.querySelector('h1')?.textContent.trim()==='实习生简历')adapter=window.JobFillAdapters.icbc;
 else if(document.querySelector('.createFormSection-repeatable .atsx-form-item'))adapter=window.JobFillAdapters.feishu;
 adapter.guard();
 for(const id of ['icbc-native-fill-progress','feishu-native-fill-progress'])document.getElementById(id)?.remove();
 window.JobFillExecutor=core.create(adapter);window.JobFillExecutorScope=location.href;
})();
