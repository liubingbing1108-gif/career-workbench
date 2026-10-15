#!/usr/bin/env python3
"""Exercise a new empty installation on a random loopback port, never the user's service."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
from init_workbench import initialize

ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='career-install-') as directory:
        initialize(directory)
        command=[sys.executable,'-u',str(ROOT/'prototypes/profile-lab/server.py'),'--port','0','--data-dir',str(Path(directory)/'.runtime/profile'),'--management-data-dir',str(Path(directory)/'.runtime/management')]
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            import queue,threading
            lines=queue.Queue()
            threading.Thread(target=lambda: lines.put(process.stdout.readline()),daemon=True).start()
            line=lines.get(timeout=30)
            if 'http://127.0.0.1:' not in line:raise RuntimeError('Temporary service did not start')
            url='http://127.0.0.1:'+line.split('http://127.0.0.1:',1)[1].strip().rstrip('/')
            def get(path):
                with urllib.request.urlopen(url+path,timeout=10) as response:return json.load(response)
            assert get('/api/health')['management'] is True
            assert get('/management/api/bootstrap')['jobs']==[]
            with urllib.request.urlopen(url+'/',timeout=10) as response:assert response.status==200
            print('PASS: clean empty installation, two modules, random local port, no model/website calls')
        finally:
            process.terminate()
            try:process.communicate(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.communicate()

if __name__=='__main__':main()
