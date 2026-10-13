"""Single-use local launch tickets; Chrome owns browser actions and permissions."""
import secrets
import os
import platform
import shutil
import subprocess
import time
from urllib.parse import urlsplit
from lab import LabError, find


def open_chrome(url):
    try:
        if platform.system() == 'Darwin' and not os.environ.get('CAREER_CHROME_BIN'):
            subprocess.run(['/usr/bin/open','-g','-a','Google Chrome',url],check=True,timeout=15,capture_output=True)
            return
        chrome = os.environ.get('CAREER_CHROME_BIN') or shutil.which('google-chrome') or shutil.which('google-chrome-stable') or shutil.which('chrome')
        if not chrome and platform.system() == 'Windows':
            from pathlib import Path
            chrome = next((str(Path(os.environ.get(key, '')) / 'Google/Chrome/Application/chrome.exe')
                           for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')
                           if (Path(os.environ.get(key, '')) / 'Google/Chrome/Application/chrome.exe').is_file()), None)
        if not chrome:raise OSError('Chrome unavailable')
        subprocess.Popen([chrome,url],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except (OSError,subprocess.SubprocessError):
        raise LabError('未能打开Chrome，请检查浏览器是否已安装',503)


class BrowserLaunch:
    def __init__(self,lab,bridge,opener=open_chrome):
        self.lab,self.bridge,self.opener=lab,bridge,opener;self.tickets={};self.controller_seen=0

    def request(self,sid,base,mode='prepare',direct=False):
        if mode not in ('prepare','focus'):raise LabError('浏览器操作无效')
        with self.lab.lock:
            session=find(self.lab.state()['sessions'],sid)
            target=session.get('website') or session.get('target') or {}
            url=target.get('url','')
            if urlsplit(url).scheme!='https':raise LabError('自动填写需要HTTPS官网链接')
            if urlsplit(url).hostname in {'mp.weixin.qq.com','www.nowcoder.com','campus.niuqizp.com'}:
                raise LabError('这是招聘信息链接，请先在管理页明确公司岗位并查找官网入口')
            if session.get('manual_reason') and mode=='prepare':raise LabError(session['manual_reason'])
            if mode=='prepare' and any(s.get('preparation',{}).get('execution',{}).get('status') in ('running','awaiting_executor') for s in self.lab.state()['sessions']):
                raise LabError('该官网正在填写，请先暂停再重新启动',409)
            if mode=='prepare' and self.bridge.status(url,sid)['connected']:
                return {'status':'ready','message':'已连接当前官网，无需打开新页面。'}
            if mode=='prepare':
                recent=next((v for v in self.tickets.values() if v['session_id']==sid and v.get('mode')==mode and time.time()-v['created']<15),None)
                if recent and session.get('preparation',{}).get('browser',{}).get('status') not in ('failed','needs_user'):
                    return {'status':'opening','ticket':next(k for k,v in self.tickets.items() if v is recent),'message':'正在连接本次岗位，请稍候。'}
            self.tickets={k:v for k,v in self.tickets.items() if time.time()-v['created']<300 and v['session_id']!=sid}
            ticket=secrets.token_urlsafe(24)
            self.tickets[ticket]={'session_id':sid,'url':url,'code':self.bridge.setup(sid)['code'],'created':time.time(),'claimed':False,'mode':mode}
            self.set_status(sid,'opening','正在打开Chrome并启动填写程序')
        try:
            if not direct and time.time()-self.controller_seen>=8:self.opener(base+'/launch-relay?launch='+ticket)
        except Exception:
            self.set_status(sid,'failed','Chrome未能启动，请检查浏览器安装后重试');raise
        return {'status':'opening','ticket':ticket,'message':'正在连接本次官网，填写进度会显示在这里。'}

    def next(self,origin,connection):
        item=self.bridge.connections.get(connection)
        if not self.bridge.allowed_origin(origin) or not item or item['origin']!=origin:
            raise LabError('填写连接无效',403)
        self.controller_seen=time.time()
        ticket=next((k for k,v in self.tickets.items() if not v['claimed'] and time.time()-v['created']<300),None)
        return {'ticket':ticket}

    def claim(self,ticket,origin):
        if not self.bridge.allowed_origin(origin):raise LabError('仅接受本机填写扩展',403)
        with self.lab.lock:
            item=self.tickets.get(ticket)
            if not item or time.time()-item['created']>=300:raise LabError('启动请求已过期，请从工作台重试',403)
            find(self.lab.state()['sessions'],item['session_id'])
            if item['claimed']:raise LabError('该启动请求已处理，请回到工作台查看进度',409)
            item['claimed']=True;item['origin']=origin
            self.set_status(item['session_id'],'connecting','填写程序已启动，正在连接官网')
            return {k:item[k] for k in ('session_id','url','code','mode')}

    def report(self,ticket,origin,status):
        if not self.bridge.allowed_origin(origin):raise LabError('仅接受本机填写扩展',403)
        messages={'permission':'请在Chrome中完成首次自动填写授权，之后无需手动开启插件',
                  'connecting':'正在打开官网并读取申请表','ready':'官网已连接，材料准备完成后确认预览即可填写',
                  'needs_user':'请在官网完成登录或打开具体申请表，系统会自动继续读取','failed':'官网连接未完成，请在工作台重新启动'}
        if status not in messages:raise LabError('浏览器进度无效')
        with self.lab.lock:
            item=self.tickets.get(ticket)
            if not item or time.time()-item['created']>=300:raise LabError('启动请求已过期',403)
            if item.get('origin')!=origin:raise LabError('启动请求与填写扩展不匹配',403)
            self.set_status(item['session_id'],status,messages[status]);return {'ok':True}

    def set_status(self,sid,status,message):
        self.lab.mutate(lambda state:find(state['sessions'],sid).setdefault('preparation',{}).update(browser={'status':status,'message':message,'updated_at':time.time()}))
