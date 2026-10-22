"""Fictional, ephemeral browser fixture; never opens the production profile."""
import tempfile
from lab import Lab,find,candidate_pending
from test_resume_skill import Stub,award
from server import make_server

def main():
    with tempfile.TemporaryDirectory(prefix='resume-skill-ui-') as directory:
        text,a=award();other,b=award('示例大学校级奖学金一等奖',extra='经学校评定。')
        lab=Lab(directory,Stub([a,b]));p=lab.upload('fiction-a.txt',text.encode())
        lab.resolve_import([{'candidate_id':c['id'],'mode':'replace'} for c in p['candidates']],{p['id']:p['revision']})
        lab.upload('fiction-b.txt',other.encode())
        server=make_server(lab);print(f'http://127.0.0.1:{server.server_port}',flush=True)
        try:server.serve_forever()
        finally:server.server_close();lab.db.close()
if __name__=='__main__':main()
