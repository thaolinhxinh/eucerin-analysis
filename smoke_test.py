"""Smoke test deployed Render API: python smoke_test.py https://YOUR-SERVICE.onrender.com"""
import os,sys,requests
base=sys.argv[1].rstrip('/') if len(sys.argv)>1 else 'http://127.0.0.1:10000'
r=requests.get(base+'/health',timeout=30)
print('health:',r.status_code,r.text[:300])
r.raise_for_status()
key=os.environ.get('ML_API_KEY')
if key:
    r=requests.post(base+'/check-source',headers={'X-API-Key':key},json={'source_id':'smoke-test','source_revision':'v0'},timeout=30)
    print('authenticated check-source:',r.status_code,r.text[:300]);r.raise_for_status()
else:print('Set ML_API_KEY locally to test protected route (never put secret in script).')
