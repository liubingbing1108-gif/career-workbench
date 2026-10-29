"""Fictional form fixture, never the active workbench."""
import tempfile,sys
from lab import Lab
from test_import_questions import Engine,SourceEngine,TEXT
from server import make_server
from profile_migration import prepare
if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='questions-ui-') as directory:
  source='--source' in sys.argv
  lab=Lab(directory,SourceEngine() if source else Engine())
  if '--current' in sys.argv:lab.mutate(lambda state:state.update(prepare(state,1000)[0]))
  lab.upload('fiction.txt',(TEXT+'\n另一次校级奖' if source else TEXT).encode());server=make_server(lab)
  print(f'http://127.0.0.1:{server.server_port}',flush=True)
  try:server.serve_forever()
  finally:server.server_close();lab.db.close()
