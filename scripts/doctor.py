#!/usr/bin/env python3
"""Read-only installation diagnostics. No model calls or private file contents."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def inspect(root=ROOT):
    result=[]
    def add(level, message): result.append((level, message))
    add('OK' if sys.version_info >= (3,11) else 'ERROR', 'Python >= 3.11')
    for name in ('markitdown','pypdf','jsonschema'):
        add('OK' if importlib.util.find_spec(name) else 'ERROR', f'Python module: {name}')
    runtime=Path(root)/'.runtime'; config=runtime/'locations.json'
    if config.is_file():
        try:
            locations=json.loads(config.read_text(encoding='utf-8'))
            valid=all((Path(root)/locations[key]/filename).is_file() for key,filename in [('profile','lab.sqlite'),('management','management.sqlite3')])
            add('OK' if valid else 'ERROR', 'Existing databases (never replaced by doctor)')
        except (OSError,ValueError,KeyError,TypeError):add('ERROR','Invalid runtime location configuration; use recovery guide')
    elif any((runtime/name).exists() for name in ('profile','management')):
        add('ERROR','Partial installation; restore locations.json, do not initialize over existing data')
    else:add('WARN','Not initialized: run python scripts/init_workbench.py')
    chrome=os.environ.get('CAREER_CHROME_BIN') or shutil.which('google-chrome') or shutil.which('google-chrome-stable') or shutil.which('chrome')
    candidates=[chrome, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    for variable in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
        if os.environ.get(variable):candidates.append(str(Path(os.environ[variable])/'Google/Chrome/Application/chrome.exe'))
    add('OK' if any(p and Path(p).is_file() for p in candidates) else 'WARN','Google Chrome; if missing, install it or set CAREER_CHROME_BIN')
    command=os.environ.get('CAREER_AGENT_COMMAND')
    if command:
        try:
            argv=json.loads(command)
            valid=isinstance(argv,list) and bool(argv) and all(isinstance(v,str) and v for v in argv) and bool(shutil.which(argv[0]) or Path(argv[0]).is_file())
        except ValueError:valid=False
        add('OK' if valid else 'ERROR','Custom Agent executable and JSON argv (no inference performed)')
        add('OK' if os.environ.get('CAREER_AGENT_ALLOW_PERSONAL_DATA')=='1' else 'WARN','Custom Agent personal-data consent; see docs/AGENT_INTEGRATION.md')
    else:
        codex=os.environ.get('PROFILE_CODEX_BIN') or shutil.which('codex')
        fallback=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
        if not codex and fallback.is_file():codex=str(fallback)
        if codex:
            try:
                help_text=subprocess.run([codex,'exec','--help'],capture_output=True,text=True,timeout=10).stdout
                required=('--ignore-user-config','--ephemeral','--output-schema','--json','--sandbox')
                compatible=all(flag in help_text for flag in required)
                add('OK' if compatible else 'WARN','Codex structured-output CLI flags; incompatible versions can use CAREER_AGENT_COMMAND')
            except (OSError,subprocess.TimeoutExpired):add('WARN','Codex executable check failed; see Agent integration guide')
        else:add('WARN','No Agent configured; manual profile/management works, automatic matching needs an Agent')
    add('INFO','Load Chrome extension manually; login, HTTPS permission and model connectivity require your own account')
    return result

def main():
    result=inspect()
    for level,message in result:print(f'[{level}] {message}')
    return int(any(level=='ERROR' for level,_ in result))

if __name__=='__main__':raise SystemExit(main())
