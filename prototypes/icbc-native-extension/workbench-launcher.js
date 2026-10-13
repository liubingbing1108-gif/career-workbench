document.querySelector('#workbench').onclick=async()=>{
 const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
 if(!tab?.url?.startsWith('https:')){document.querySelector('#result').textContent='请先打开招聘官网，再从官网页打开此扩展。';return;}
 await chrome.tabs.create({url:chrome.runtime.getURL('workbench.html')+'?tabId='+tab.id});
};
