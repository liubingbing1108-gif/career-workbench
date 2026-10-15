"""Read Codex JSONL until a terminal turn event, not until background teardown."""
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from urllib.request import getproxies


def model_environment():
    env = os.environ.copy()
    # macOS GUI proxy settings are not necessarily exported to a subprocess.
    # Respect explicit caller settings and reuse only the user's existing proxy.
    if sys.platform == 'darwin':
        proxies = getproxies()
        for protocol in ('http', 'https', 'no'):
            key = protocol + '_proxy'
            if key not in env and key.upper() not in env and proxies.get(protocol):
                env[key.upper()] = proxies[protocol]
        # The Responses transport also uses WebSockets. HTTP(S)_PROXY alone
        # does not cover every CLI transport; keep explicit WS settings intact.
        for protocol, source in (('ws', 'http'), ('wss', 'https')):
            key = protocol + '_proxy'
            if key not in env and key.upper() not in env:
                proxy = env.get(source + '_proxy', env.get(source.upper() + '_PROXY'))
                if proxy:
                    env[key.upper()] = proxy
    return env


def run_codex(command, *, input, timeout, cwd):
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                               cwd=cwd, env=model_environment(), start_new_session=os.name != 'nt')
    events = queue.Queue()
    stdout, stderr, size = [], [], 0
    ended = set()

    def read(stream, name):
        try:
            for line in stream:
                events.put((name, line))
        finally:
            events.put((name, None))

    def write():
        try:
            process.stdin.write(input)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    readers = [threading.Thread(target=read, args=(process.stdout, 'stdout'), daemon=True),
               threading.Thread(target=read, args=(process.stderr, 'stderr'), daemon=True),
               threading.Thread(target=write, daemon=True)]
    for worker in readers:
        worker.start()
    try:
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout, output=''.join(stdout), stderr=''.join(stderr))
            try:
                name, line = events.get(timeout=min(.2, remaining))
            except queue.Empty:
                if len(ended) == 2 and process.poll() is not None:
                    return subprocess.CompletedProcess(command, process.returncode, ''.join(stdout), ''.join(stderr))
                continue
            if line is None:
                ended.add(name)
                continue
            if name == 'stderr':
                stderr.append(line)
                if sum(map(len, stderr)) > 64000:
                    stderr = [''.join(stderr)[-64000:]]
                continue
            stdout.append(line)
            size += len(line)
            if size > 4_000_000:
                return subprocess.CompletedProcess(command, 1, '', 'output limit exceeded')
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') in {'turn.completed', 'turn.failed'}:
                return subprocess.CompletedProcess(command, 0 if event['type'] == 'turn.completed' else 1,
                                                   ''.join(stdout), ''.join(stderr))
    finally:
        if process.poll() is None:
            try:
                if os.name == 'nt':process.terminate()
                else:os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':process.kill()
                else:os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1)
            except ProcessLookupError:
                pass
        for worker in readers:
            worker.join(timeout=1)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def failure_diagnostics(stdout, stderr, elapsed):
    def text(value):return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
    out, err = text(stdout), text(stderr)
    combined = (out + '\n' + err).lower()
    code = ('connection_failed' if 'workspace routing discovery failed' in combined or 'failed to refresh available models' in combined or 'error sending request for url' in combined
            else 'capacity' if 'at capacity' in combined
            else 'auth_failed' if any(x in combined for x in ('unauthorized', 'authentication failed', 'invalid_api_key'))
            else 'timeout')
    # Only fixed labels and counts are persisted. Never retain raw model text,
    # URLs, headers, prompts, credentials, or provider stderr in the profile DB.
    return {'code': code, 'elapsed_seconds': round(elapsed, 2),
            'workspace_routing_failed': 'workspace routing discovery failed' in combined,
            'model_catalog_failed': 'failed to refresh available models' in combined,
            'skills_context_overflow': 'exceeded skills context budget' in combined,
            'reconnect_count': out.count('Reconnecting...'),
            'output_received': '"agent_message"' in out}
