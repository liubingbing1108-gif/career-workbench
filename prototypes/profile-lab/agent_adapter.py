"""Provider-neutral JSON subprocess adapter; configured by the local user only."""
import json
import os
import subprocess
import tempfile
from urllib.parse import urlsplit


def call_agent(command, prompt, schema, purpose, web_search, timeout):
    from recognizer import RecognitionError
    from jsonschema import Draft202012Validator
    try:
        argv = json.loads(command)
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
            raise ValueError()
    except (ValueError, TypeError):
        raise RecognitionError('CAREER_AGENT_COMMAND 必须为可执行文件及参数的 JSON 数组', 'agent_config')
    if not web_search and os.environ.get('CAREER_AGENT_ALLOW_PERSONAL_DATA') != '1':
        raise RecognitionError('请先确认自选 Agent 的资料处理方式，再设置 CAREER_AGENT_ALLOW_PERSONAL_DATA=1', 'agent_consent')
    request = {'protocol_version': 1, 'task': 'public_lookup' if web_search else 'structured_inference',
               'instructions': purpose, 'prompt': prompt, 'output_schema': schema,
               'capabilities': {'public_web': web_search, 'shell': False, 'files': False, 'browser_actions': False}}
    # No shell interpolation, project cwd, raw provider diagnostics or automatic fallback.
    try:
        with tempfile.TemporaryDirectory(prefix='career-agent-') as directory:
            run = subprocess.run(argv, input=json.dumps(request, ensure_ascii=False), text=True,
                                 capture_output=True, timeout=timeout, cwd=directory)
    except subprocess.TimeoutExpired:
        raise RecognitionError('Agent 响应超时，资料未改动，可以重试', 'timeout')
    except OSError:
        raise RecognitionError('无法启动自选 Agent，请检查命令和绝对路径', 'agent_config')
    if run.returncode or len(run.stdout) > 4_000_000:
        raise RecognitionError('Agent 执行失败或响应过大，未采用结果')
    try:
        response = json.loads(run.stdout)
        if not isinstance(response, dict) or response.get('protocol_version') != 1:
            raise ValueError()
        result = response['result']
        if not Draft202012Validator(schema).is_valid(result):
            raise ValueError()
        usage = response.get('usage', {})
        if not isinstance(usage, dict):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise RecognitionError('Agent 返回格式不符合约定，未写入资料', 'invalid_output')
    # Allow only explicit public evidence metadata into official-source verification.
    pages = []
    for page in response.get('web_pages', []) if isinstance(response.get('web_pages', []), list) else []:
        if not isinstance(page, dict) or not isinstance(page.get('url'), str):
            continue
        p = urlsplit(page['url'])
        if p.scheme != 'https' or not p.hostname or p.username or p.password:
            continue
        pages.append({key: str(page.get(key, ''))[:16000] for key in ('url', 'title', 'snippet')} | {'opened': page.get('opened') is True})
    if web_search and not any(p['opened'] for p in pages):
        raise RecognitionError('Agent 没有提供实际打开的公开网页证据，未采用推测网址', 'search_not_executed')
    return result, {'web_pages': pages} if web_search else {}
