#!/usr/bin/env python3
"""Validate the distributable documentation without private archives."""
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit
ROOT=Path(__file__).resolve().parents[1]
required=['README.md','AGENTS.md','START_HERE.md','SECURITY.md','CONTRIBUTING.md','CHANGELOG.md','GOVERNANCE.md','docs/AGENT_PLAYBOOK.md','docs/CAPABILITIES.json','docs/CONTINUITY.md','docs/PROJECT_ACTIVITY.md']+['docs/'+n+'.md' for n in ('SETUP','PRODUCT_REQUIREMENTS','HANDOFF_CONTEXT','ARCHITECTURE','DATA_AND_API','AGENT_INTEGRATION','OPERATIONS','TESTING','RELEASE','ROADMAP','DECISIONS','DISCUSSION_AND_ACCEPTANCE')]
errors=[f'Missing {name}' for name in required if not (ROOT/name).is_file()]
count=0
for p in ROOT.rglob('*.md'):
    if set(p.relative_to(ROOT).parts)&{'.runtime','.git','.venv','node_modules','__pycache__'}:continue
    text=re.sub(r'```[\s\S]*?```','',p.read_text())
    for target in re.findall(r'\]\(([^)]+)\)',text):
        target=target.strip('<>').split('#')[0].split('?')[0]
        if not target or urlsplit(target).scheme or target.startswith('/'):continue
        count+=1
        if not (p.parent/unquote(target)).exists():errors.append(f'{p.relative_to(ROOT)}: broken relative link')
if errors:raise SystemExit('\n'.join(errors))
print(f'PASS documentation; {count} relative links; no private archive required.')
