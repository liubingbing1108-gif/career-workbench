#!/usr/bin/env python3
"""Check a reviewed source tree (or Git tracked files); print paths, never matched secrets."""
import argparse
from pathlib import Path
import re
import subprocess

BLOCKED_PARTS = {'.runtime','evidence','screenshots','__pycache__','node_modules','.venv','legacy','.env','context'}
BLOCKED_SUFFIXES = {'.sqlite','.sqlite3','.db','.pdf','.docx','.doc','.png','.jpg','.jpeg','.webp','.zip','.log','.pid','.pyc'}
PATTERNS = {
    'personal absolute path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private applicant identifier': re.compile(r'[?&](?:userId|applicantId|candidateId)=\d{5,}',re.I),
    'credential': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{25,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'),
    'personal email provider': re.compile(r'\b[A-Za-z0-9._%+-]+@(?:qq|163|126|gmail|outlook|hotmail)\.com\b',re.I),
}

def check(root, tracked=False):
    root=Path(root).resolve()
    paths=[root/p for p in subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0') if p] if tracked else [p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts]
    errors=[]
    for path in paths:
        rel=path.relative_to(root)
        if path.is_symlink() or set(rel.parts)&BLOCKED_PARTS or path.suffix.lower() in BLOCKED_SUFFIXES or path.name.startswith('.env') and path.name!='.env.example':
            errors.append(f'{rel}: private/generated file is not distributable');continue
        try:text=path.read_text(encoding='utf-8')
        except (UnicodeError,OSError):errors.append(f'{rel}: unexpected binary/unreadable file');continue
        for reason,pattern in PATTERNS.items():
            for m in pattern.finditer(text):
                errors.append(f'{rel}:{text.count(chr(10),0,m.start())+1}: {reason}')
    return paths,errors

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',nargs='?',default='.');parser.add_argument('--tracked',action='store_true');args=parser.parse_args()
    paths,errors=check(args.root,args.tracked)
    if errors:raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(paths)} source files checked; no blocked paths or high-confidence secret patterns. Manual privacy review is still required.')
