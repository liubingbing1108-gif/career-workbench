#!/usr/bin/env python3
"""Offline regression suite; all databases are temporary and all identities fictional."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
commands = [
    [sys.executable, 'scripts/check_project.py'],
    [sys.executable, "prototypes/profile-lab/generate_samples.py"],
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'prototypes/profile-lab', '-p', 'test_*.py'],
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'prototypes/management-lab', '-p', 'test_*.py'],
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts', '-p', 'test_*.py'],
    ['node', '--test', *[str(p.relative_to(ROOT)) for p in sorted((ROOT/'prototypes/icbc-native-extension').glob('*.cjs'))],
     *[str(p.relative_to(ROOT)) for p in sorted((ROOT/'prototypes/profile-lab').glob('test-*.cjs'))],
     'prototypes/management-lab/test_integration.js'],
]
for command in commands:
    subprocess.run(command, cwd=ROOT, check=True)
if '--ui' in sys.argv:
    env = {**os.environ, 'PYTHON': sys.executable}
    for name in ('test_browser.cjs','test_requirement_browser.cjs','test_product.cjs','test_recovery_browser.cjs','test_material_controls_browser.cjs','test_partial_fill_browser.cjs','test_retry_browser.cjs','test_language_browser.cjs','test_profile_library_browser.cjs','test_profile_hierarchy_browser.cjs','test_profile_names_browser.cjs','test_confirmation_browser.cjs','test_progress_browser.cjs','test_resume_skill_browser.cjs','test_import_questions_browser.cjs','test_profile_flat_browser.cjs','test_current_material_browser.cjs','test_correction_browser.cjs'):
        subprocess.run(['node',str(ROOT/'prototypes/profile-lab'/name)],cwd=ROOT,env=env,check=True)
print('PASS: offline suite complete. No real website or model was used.')
