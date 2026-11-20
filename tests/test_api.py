"""Integration tests use the REAL Eucerin source and frozen model; failures are fixtures only."""
import os,sys,io,hashlib,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TEST_STORAGE=Path(tempfile.mkdtemp(prefix='eucerin_auto_api_test_'))
os.environ['STORAGE_DIR']=str(TEST_STORAGE)
os.environ['ML_API_KEY']='TEST_SECRET_ONLY_NEVER_DEPLOY'
os.environ['APP_MODE']='research'
from app.main import app
from app import store
from app.reporting import OUTPUT_FILES
from app.data_validation import validate_csv
from app.forecast import get_assets
from app.chapter6_pipeline import features_from_origin, NUM

DATA_PATH=Path(os.getenv('EUCERIN_TEST_DATA',str(ROOT/'reference/historical_eucerin_confirmed.csv')))
if not DATA_PATH.is_file():
    pytest.skip(
        'Dataset integration tests require a private CSV; set EUCERIN_TEST_DATA to its path.',
        allow_module_level=True,
    )
DATA=DATA_PATH.read_bytes()
HEAD={'X-API-Key':os.environ['ML_API_KEY']}

def post(client,data=DATA,rev='v1',source='fixture-file-id'):
    return client.post('/predict-file',params={'source_id':source,'source_revision':rev},
      headers=HEAD,files={'file':('historical_eucerin_confirmed.csv',data,'text/csv')})

def csv_edit(modifier):
    d=pd.read_csv(io.BytesIO(DATA),dtype={'product_id':str})
    d=modifier(d.copy())
    return d.to_csv(index=False).encode('utf-8-sig')

def test_model_loaded_during_application_startup():
    with patch('app.main.get_assets') as load_model:
        with TestClient(app):
            pass
    load_model.assert_called_once_with()

def test_full_lifecycle_real_dataset():
 with TestClient(app) as c:
    health=c.get('/health')
    assert health.status_code==200
    assert health.json()['status']=='ok'
    assert health.json()['model_loaded'] is True
    assert health.json()['forecast_ready'] is True
    assert health.json()['trained_skus']==73
    assert c.post('/check-source',json={'source_id':'fixture-file-id','source_revision':'v1'}).status_code==401
    assert post(c,data=b'broken').status_code==422
    chk=c.post('/check-source',json={'source_id':'fixture-file-id','source_revision':'v1'},headers=HEAD).json()
    assert chk['changed'] is True
    r=post(c)
    assert r.status_code==200,r.text
    x=r.json()
    assert x['status']=='ready' and x['summary']['trained_skus']==73
    assert x['summary']['forecast_rows']==511
    assert x['summary']['predicted_sale_sku_days']==77
    assert abs(x['summary']['expected_sale_sku_days']-81.177975)<0.03
    assert len(x['files_pending'])==len(OUTPUT_FILES)
    rid=x['run_id']
    # Same file *before* Telegram delivery resumes a run instead of duplicating outputs
    again=post(c).json();assert again['run_id']==rid and again['status']=='ready'
    denied=c.get(f'/results/{rid}/FactOccurrenceForecast_PowerBI.csv')
    assert denied.status_code==401
    for fname in OUTPUT_FILES:
        data=c.get(f'/results/{rid}/{fname}',headers=HEAD)
        assert data.status_code==200,(fname,data.text[:250])
        assert len(data.content)>30
    fact=pd.read_csv(store.ROOT/'runs'/rid/'FactOccurrenceForecast_PowerBI.csv',dtype={'ProductID':str})
    dim=pd.read_csv(store.ROOT/'runs'/rid/'DimSKU_Behavior.csv',dtype={'ProductID':str})
    assert fact.duplicated(['RunID','ProductID','ForecastDate']).sum()==0
    assert fact.ProbabilityOfSale.between(0,1).all()
    assert dim.ProductID.nunique()==73 and len(dim)==73
    assert len(fact)==7*dim.ProductID.nunique()
    assert c.post(f'/runs/{rid}/reserve-notification',headers=HEAD).status_code==409
    for i,f in enumerate(OUTPUT_FILES):
        res=c.post(f'/runs/{rid}/ack-file',headers=HEAD,json={'file_name':f,'drive_file_id':f'DRIVE_TEST_{i}'})
        assert res.status_code==200,res.text
    reservation=c.post(f'/runs/{rid}/reserve-notification',headers=HEAD)
    assert reservation.status_code==200 and reservation.json()['send'] is True
    assert '81.18' in reservation.json()['telegram_text']
    assert c.post(f'/runs/{rid}/reserve-notification',headers=HEAD).json()['send'] is False
    sent=c.post(f'/runs/{rid}/complete',headers=HEAD,json={'telegram_message_id':'SIMULATED_MSG_100'})
    assert sent.status_code==200
    assert post(c).json()['status']=='unchanged'
    assert c.post('/check-source',json={'source_id':'fixture-file-id','source_revision':'v1'},headers=HEAD).json()['changed'] is False
    assert c.get('/history',headers=HEAD).json()['runs'][0]['status']=='delivered'
    print('REAL DATA PASS:',{k:x['summary'][k] for k in ('trained_skus','forecast_rows','expected_sale_sku_days','predicted_sale_sku_days','alert_count')})

@pytest.mark.parametrize('scenario,modifier',[
  ('missing_col',lambda d:d.drop(columns=['units_sold'])),
  ('duplicate',lambda d:pd.concat([d,d.iloc[[0]]],ignore_index=True)),
  ('negative',lambda d:d.assign(units_sold=np.where(d.index==0,-10,d.units_sold))),
  ('missing_day',lambda d:d.iloc[1:].copy()),
])
def test_bad_csv_rejected(scenario,modifier):
    with TestClient(app) as c:
        raw=csv_edit(modifier)
        r=post(c,data=raw,rev=scenario,source='test-'+scenario)
        assert r.status_code==422,(scenario,r.text)

def test_unknown_sku_not_fabricated_and_model_scope_dynamic():
    d=pd.read_csv(io.BytesIO(DATA),dtype={'product_id':str})
    extra=d[d.product_id.eq(str(d.product_id.iloc[0]))].copy()
    extra.product_id='9999999999999999999'  # synthetic fixture only; never in reports
    raw=pd.concat([d,extra]).to_csv(index=False).encode('utf-8')
    with TestClient(app) as c:
        x=post(c,data=raw,rev='newsku',source='newSKU').json()
        assert x['status']=='ready',x
        assert x['summary']['excluded_untrained_skus']==22  # existing 21 untrained + 1 new fixture
        assert x['summary']['trained_skus']==73
        assert x['summary']['forecast_rows']==7*x['summary']['trained_skus']

def test_no_future_label_leakage():
    panel,_,_=validate_csv(DATA)
    cutoff=pd.Timestamp('2026-10-05')
    original=features_from_origin(panel,cutoff).sort_values(['ProductID','Horizon']).reset_index(drop=True)
    copy=panel.copy();copy.loc[copy.Date.gt(cutoff),'UnitsSold']=99999
    changed=features_from_origin(copy,cutoff).sort_values(['ProductID','Horizon']).reset_index(drop=True)
    pd.testing.assert_frame_equal(original[['ProductID']+NUM],changed[['ProductID']+NUM])

def test_unavailable_model_and_external_failures_not_falsely_successful():
    with TestClient(app) as c:
        with patch('app.main.get_assets',side_effect=RuntimeError('model offline')):
            assert c.get('/health').status_code==503
        # Simulate failure *after* Drive acknowledgements and before Telegram delivery.
        altered=csv_edit(lambda d: d.assign(units_sold=np.where(d.index==0,d.units_sold+1,d.units_sold)))
        response=post(c,data=altered,rev='notifyfail',source='failtest')
        assert response.status_code==200,response.text
        rid=response.json()['run_id']
        for i,f in enumerate(OUTPUT_FILES):
            r=c.post(f'/runs/{rid}/ack-file',headers=HEAD,json={'file_name':f,'drive_file_id':f'SIM_{i}'})
            assert r.status_code==200
        assert c.post(f'/runs/{rid}/reserve-notification',headers=HEAD).json()['send'] is True
        assert c.get(f'/runs/{rid}',headers=HEAD).json()['status']=='notification_reserved'
        # Automatic second attempt must NOT re-send Telegram, requiring operator reconciliation.
        assert c.post(f'/runs/{rid}/reserve-notification',headers=HEAD).json()['send'] is False


def test_workflow_graph_structural():
    import json
    a=json.load(open(ROOT/'n8n/EUCERIN_n8n_Complete.json',encoding='utf-8'))
    ids={n['name'] for n in a['nodes']}
    assert len(ids)==len(a['nodes'])
    for src,conn in a['connections'].items():
        assert src in ids
        for branch in conn['main']:
            for node in branch:assert node['node'] in ids
    assert any(n['type']=='n8n-nodes-base.googleDrive' for n in a['nodes'])
    assert any(n['type']=='n8n-nodes-base.telegram' for n in a['nodes'])
    for n in a['nodes']:
        assert 'TEST_SECRET' not in json.dumps(n)
    e=json.load(open(ROOT/'n8n/EUCERIN_n8n_Error_Handler.json',encoding='utf-8'))
    assert any(x['type']=='n8n-nodes-base.errorTrigger' for x in e['nodes'])
