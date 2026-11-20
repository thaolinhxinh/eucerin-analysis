import json,os,sys
import ast
from pathlib import Path
p=Path(__file__).resolve().parents[1]

def test_render_blueprint_and_docker():
    import yaml
    y=yaml.safe_load((p/'render.yaml').read_text())
    s=y['services'][0]
    assert s['runtime']=='docker' and s['plan']!='free'
    assert s['disk']['mountPath']=='/app/storage'
    assert s['disk']['sizeGB']>=1
    assert any(x['key']=='ML_API_KEY' and x.get('sync') is False for x in s['envVars'])
    assert 'start_server.py' in (p/'Dockerfile').read_text()
    assert s['branch']=='main'
    assert s['autoDeployTrigger']=='commit'

def test_private_data_is_excluded_but_frozen_model_is_versionable():
    ignore=(p/'.gitignore').read_text()
    assert '.env' in ignore
    assert 'reference/historical_eucerin_confirmed.csv' in ignore
    assert 'sample_outputs/' in ignore
    assert 'storage/' in ignore
    assert '!models/Model_Classification.joblib' not in ignore
    assert (p/'models/Model_Classification.joblib').stat().st_size < 100*1024*1024

def test_docker_context_omits_private_dataset_but_keeps_runtime_metrics():
    dockerignore=(p/'.dockerignore').read_text()
    dockerfile=(p/'Dockerfile').read_text()
    assert 'reference/*' in dockerignore
    assert '!reference/Validation_Metrics.csv' in dockerignore
    assert '!reference/Holdout_Metrics.csv' in dockerignore
    assert 'COPY reference/Validation_Metrics.csv reference/Holdout_Metrics.csv ./reference/' in dockerfile
    assert 'COPY reference ./reference' not in dockerfile

def test_model_assets_are_loaded_in_fastapi_lifespan():
    tree=ast.parse((p/'app/main.py').read_text(encoding='utf-8'))
    lifespan=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=='lifespan')
    assert any(isinstance(x,ast.Expr) and isinstance(x.value,ast.Call)
               and isinstance(x.value.func,ast.Name) and x.value.func.id=='get_assets'
               for x in lifespan.body)

def test_workflow_config_all_url_fields():
    w=json.loads((p/'n8n/EUCERIN_Render_n8n_Workflow.json').read_text())
    names={n['name'] for n in w['nodes']}
    assert '02 | Config - Vercel, Drive, Telegram' in names
    assert not w['active']
    assert w['settings']['timezone']=='Asia/Ho_Chi_Minh'
    for n in w['nodes']:
        if n['type']=='n8n-nodes-base.httpRequest':
            assert 'apiBaseUrl' in n['parameters']['url']
    for edges in w['connections'].values():
        for branch in edges['main']:
            for e in branch: assert e['node'] in names
