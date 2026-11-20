"""Start API on Render; normalize mounted disk permissions then drop privileges."""
import os,sys
from pathlib import Path
p=Path(os.environ.get('STORAGE_DIR','/app/storage'))
p.mkdir(parents=True,exist_ok=True)
if os.geteuid()==0:
    os.chown(p,10001,10001)
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
if not os.access(p,os.W_OK):
    print('ERROR: STORAGE_DIR is not writable. Configure Render persistent disk at /app/storage.',file=sys.stderr)
    raise SystemExit(1)
port=int(os.environ.get('PORT','10000'))
if port<1 or port>65535:raise SystemExit('Invalid PORT')
os.execvp('uvicorn',['uvicorn','app.main:app','--host','0.0.0.0','--port',str(port),'--workers','1','--proxy-headers'])
