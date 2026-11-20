import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vercel_routes_fastapi_from_singapore_with_bounded_function_time():
    config = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
    function = config['functions']['app/main.py']
    assert config['regions'] == ['sin1']
    assert function['maxDuration'] == 300
    assert 'reference/historical_eucerin_confirmed.csv' in function['excludeFiles']
    assert 'sample_outputs/**' in function['excludeFiles']


def test_vercel_storage_dependencies_are_declared():
    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'psycopg[binary]' in requirements
    assert 'vercel-blob' in requirements


def test_local_environment_secrets_are_excluded_from_vercel_cli_uploads():
    ignored = (ROOT / '.vercelignore').read_text(encoding='utf-8').splitlines()
    required = {
        '.env', '.env.*', '.secrets/', 'secrets/', 'credentials/', 'token.json',
        'client_secret*.json', '*credentials*.json', '*service-account*.json',
        '*.pem', '*.key', '*.p12', '*.pfx',
    }
    assert required <= set(ignored)


def test_vercel_python_version_is_pinned_to_dependency_compatible_runtime():
    assert (ROOT / '.python-version').read_text(encoding='utf-8').strip() == '3.12'


def test_n8n_workflow_defaults_to_vercel_host_placeholder():
    workflow = json.loads((ROOT / 'n8n/EUCERIN_Render_n8n_Workflow.json').read_text(encoding='utf-8'))
    config = next(node for node in workflow['nodes'] if node['name'].startswith('02 | Config'))
    code = config['parameters']['jsCode']
    assert 'https://REPLACE_WITH_VERCEL_HOST.vercel.app' in code


def test_vercel_end_to_end_workflow_uses_verified_host_and_safe_placeholders():
    workflow = json.loads((ROOT / 'n8n/EUCERIN_Vercel_EndToEnd.json').read_text(encoding='utf-8'))
    nodes = {node['name']: node for node in workflow['nodes']}
    assert workflow['active'] is False
    assert workflow['settings']['timezone'] == 'Asia/Ho_Chi_Minh'
    assert {'01A | Manual Trigger', '01B | Daily 09:00 ICT'} <= set(nodes)
    config = nodes['02 | Config - Vercel, Drive, Telegram']['parameters']['jsCode']
    assert "https://eucerin-ml-automation.vercel.app" in config
    assert 'REPLACE_WITH_SOURCE_CSV_FILE_ID' in config
    assert 'REPLACE_WITH_OUTPUT_FOLDER_ID' in config
    assert 'REPLACE_WITH_TELEGRAM_CHAT_ID' in config
    assert 'ML_API_KEY' not in json.dumps(workflow)
    assert all(node.get('retryOnFail') is True for node in workflow['nodes']
               if node['type'] == 'n8n-nodes-base.httpRequest'
               and node['name'] not in {'10 | API: Download each CSV'})
    assert any(node['type'] == 'n8n-nodes-base.googleDrive' for node in workflow['nodes'])
    assert any(node['type'] == 'n8n-nodes-base.telegram' for node in workflow['nodes'])
    errors = json.loads((ROOT / 'n8n/EUCERIN_Vercel_Error_Handler.json').read_text(encoding='utf-8'))
    assert any(node['type'] == 'n8n-nodes-base.errorTrigger' for node in errors['nodes'])
    assert all(edge['node'] in nodes for outputs in workflow['connections'].values()
               for branch in outputs['main'] for edge in branch)


def test_vercel_runtime_selects_postgres_and_temporary_workspace():
    source = (ROOT / 'app/store.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    assert "os.getenv('VERCEL') == '1'" in source
    assert 'DATABASE_URL' in source
    assert "Path('/tmp/eucerin')" in source
    assert any(isinstance(n, ast.FunctionDef) and n.name == 'store_artifacts' for n in tree.body)


def test_vercel_ingress_limit_is_below_platform_body_cap():
    source = (ROOT / 'app/data_validation.py').read_text(encoding='utf-8')
    assert 'VERCEL_MAX_BYTES=4*1024*1024' in source.replace(' ', '')
    assert "os.getenv('VERCEL') == '1'" in source


def test_generated_artifacts_are_persisted_before_run_record_is_created():
    source = (ROOT / 'app/main.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
    calls = sorted((n.lineno, n.func.attr) for n in ast.walk(prepare)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute))
    positions = {name: line for line, name in calls}
    assert positions['store_artifacts'] < positions['create_run']
