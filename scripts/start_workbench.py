#!/usr/bin/env python3
"""Start the local product as a user-owned background job, retaining existing data."""
import json
import argparse
import signal
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
LABEL = 'local.toudi.workbench'


def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8768/api/health', timeout=2) as response:
            data=json.load(response)
            return data.get('product') == '投递工作台' and data.get('management') is True
    except Exception:
        return False


def main():
    parser=argparse.ArgumentParser(description='Start the existing local Career Workbench. Initialize new installations separately.')
    parser.add_argument('--restart',action='store_true',help='Restart the verified local service (macOS/Linux only)')
    args=parser.parse_args()
    paths=RUNTIME/'locations.json'
    configured=json.loads(paths.read_text()).get('python') if paths.exists() else None
    bundled=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
    python=sys.executable if sys.prefix!=sys.base_prefix else configured or (str(bundled) if bundled.exists() else sys.executable)
    if args.restart or not health():
        check=subprocess.run([python,'-c','import markitdown, pypdf, jsonschema'],capture_output=True)
        if check.returncode:
            raise SystemExit('运行环境缺少文档转换依赖，请使用已安装 requirements.txt 的 Python 启动；现有服务未停止。')
    if args.restart and os.name=='nt':
        raise SystemExit('Windows 请先关闭原工作台服务，再运行启动命令。')
    if args.restart:
        pid_file=RUNTIME/'server.pid'
        if pid_file.exists():
            pid=int(pid_file.read_text())
            result=subprocess.run(['/bin/ps','-p',str(pid),'-o','command='],capture_output=True,text=True)
            if str(ROOT/'prototypes/profile-lab/server.py') in result.stdout and '--port 8768' in result.stdout:
                os.kill(pid,signal.SIGTERM)
                for _ in range(30):
                    if not health():break
                    time.sleep(.1)
    if health():
        print('已运行：http://127.0.0.1:8768/');return
    if not paths.exists():
        raise SystemExit('缺少原资料目录配置，拒绝启动空白资料库。请恢复 .runtime/locations.json。')
    locations=json.loads(paths.read_text())
    locations={key:str((ROOT/Path(locations[key])).resolve()) for key in ('profile','management')}
    for key,filename in [('profile','lab.sqlite'),('management','management.sqlite3')]:
        if not (Path(locations[key])/filename).is_file():
            raise SystemExit('未找到原资料目录，未创建空白资料。')
    command=[python,str(ROOT/'prototypes/profile-lab/server.py'),'--port','8768','--data-dir',locations['profile'],'--management-data-dir',locations['management']]
    RUNTIME.mkdir(exist_ok=True)
    for name in ['server.out.log','server.err.log']:
        file=RUNTIME/name;file.touch(exist_ok=True);file.chmod(0o600)
    # A separate process session survives the launching terminal/Codex execution.
    with (RUNTIME/'server.out.log').open('ab') as out,(RUNTIME/'server.err.log').open('ab') as err:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,close_fds=True)
    (RUNTIME/'server.pid').write_text(str(process.pid))
    for _ in range(40):
        if health():print('已启动：http://127.0.0.1:8768/');return
        time.sleep(.2)
    raise SystemExit('未启动成功；请查看 .runtime/server.err.log。原资料未删除。')

if __name__=='__main__':main()
