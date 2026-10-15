#!/usr/bin/env python3
"""Install this checkout into its own venv; never replace user databases."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description='Install Career Workbench in a local virtual environment')
    parser.add_argument('--dev', action='store_true', help='Also install Python test dependencies')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit('需要 Python 3.11 或更新版本。')
    environment = ROOT / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    elif not python.is_file():
        raise SystemExit('.venv 已存在但不是有效环境；未覆盖，请检查该目录。')
    requirement = 'requirements-dev.lock' if args.dev else 'requirements.txt'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / requirement)], check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
    runtime = ROOT / '.runtime'
    if not (runtime / 'locations.json').exists():
        subprocess.run([str(python), str(ROOT / 'scripts/init_workbench.py')], check=True)
    subprocess.run([str(python), str(ROOT / 'scripts/doctor.py')], check=True)
    print('安装完成。启动命令：')
    print(f'"{python}" "{ROOT / "scripts/start_workbench.py"}"')

if __name__ == '__main__':
    main()
