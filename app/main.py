"""FastAPI production-facing model service. n8n is the orchestrator."""
import os,io,json,hashlib,hmac,threading,re,logging
from contextlib import asynccontextmanager
from pathlib import Path
import pandas as pd
from fastapi import FastAPI, File, UploadFile, Header, HTTPException,Depends
from fastapi.responses import FileResponse,Response
from fastapi.concurrency import run_in_threadpool
from . import store
from .schemas import SourceCheck,FileAcknowledgement,TelegramReceipt
from .forecast import get_assets,forecast
from .data_validation import validate_csv,MAX_BYTES
from .reporting import OUTPUT_FILES,make_outputs,build_telegram

LOGGER=logging.getLogger('eucerin')
ROOT=Path(__file__).resolve().parent.parent
REFERENCE=ROOT/'reference'
LOCK=threading.RLock()

@asynccontextmanager
async def lifespan(app):
    store.init()
    get_assets()
    yield

app=FastAPI(title='Eucerin ML Automation API',version='2.0.0',lifespan=lifespan)


def api_auth(x_api_key:str|None=Header(default=None,alias='X-API-Key')):
    key=os.getenv('ML_API_KEY','')
    if not key: raise HTTPException(503,'Server API key not configured')
    if not x_api_key or not hmac.compare_digest(x_api_key,key):
        raise HTTPException(401,'Unauthorized')

@app.get('/health')
def health():
    try:
        _,c,ids,v=get_assets()
        return {'status':'ok','model_loaded':True,'forecast_ready':True,
                'model_version':v,'trained_skus':len(ids),'mode':os.getenv('APP_MODE','research')}
    except Exception:
        raise HTTPException(503,'Model unavailable')

@app.post('/check-source',dependencies=[Depends(api_auth)])
def check_source(body:SourceCheck):
    _,_,_,version=get_assets()
    found=store.same_source_delivered(body.source_id,body.source_revision,version)
    return {'changed':found is None,'reason':'already_delivered' if found else 'new_or_unfinished',
         'model_version':version,'previous_run_id':found['run_id'] if found else None}


def prepare(raw,source_id,source_revision):
    with LOCK:
        model,config,ids,modelver=get_assets()
        sha=hashlib.sha256(raw).hexdigest()
        old=store.get_by_hash(sha,modelver)
        if old:
            if old['status']=='delivered':
                return {'status':'unchanged','changed':False,'run_id':old['run_id'],'model_version':modelver,'message':'Already delivered for identical source hash and model version'}
            summary=json.loads(old['summary_json'])
            return {'status':'ready','changed':True,'run_id':old['run_id'],'model_version':modelver,
              'files_pending':[f for f in OUTPUT_FILES if f not in store.uploads(old['run_id'])],
              'files_uploaded':store.uploads(old['run_id']),'summary':summary}
        panel,origin,diagnostics=validate_csv(raw)
        features,conf,version=forecast(panel,origin)
        run_id=origin.strftime('%Y%m%d')+'_'+sha[:10]+'_'+modelver[:8]
        outdir=store.ROOT/'runs'/run_id
        outdir.mkdir(exist_ok=True,parents=True)
        summary=make_outputs(panel,origin,features,conf,version,run_id,outdir,diagnostics,REFERENCE)
        # Export run-history snapshot; durable run state lives in SQLite or Postgres.
        prior=store.history()
        prior.insert(0,{'run_id':run_id,'source_sha':sha,'model_version':version,
          'source_id':source_id,'source_revision':source_revision,'status':'prepared',
          'as_of_date':str(origin.date()),'telegram_message_id':None,
          'created_at':store.now(),'updated_at':store.now()})
        pd.DataFrame(prior).to_csv(outdir/'Model_Run_History.csv',index=False,encoding='utf-8-sig')
        store.store_artifacts(run_id,outdir,OUTPUT_FILES)
        store.create_run(run_id,sha,version,source_id,source_revision,str(origin.date()),summary)
        return {'status':'ready','changed':True,'run_id':run_id,'model_version':modelver,
          'files_pending':list(OUTPUT_FILES),'files_uploaded':{},'summary':summary}

@app.post('/predict-file',dependencies=[Depends(api_auth)])
async def predict_file(file:UploadFile=File(...),source_id:str='manual',source_revision:str='manual'):
    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(400,'Upload full historical .csv only')
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise HTTPException(413,f'CSV >{MAX_BYTES // (1024*1024)} MB')
    if not re.fullmatch(r'[\w.:/\-]{1,512}',source_id) or len(source_revision)>512:
        raise HTTPException(422,'Source ID/revision invalid')
    try:return await run_in_threadpool(prepare,raw,source_id,source_revision)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    except Exception:
        LOGGER.exception('ML inference failed')
        raise HTTPException(500,'Internal ML inference error')

@app.get('/results/{run_id}/{file_name}',dependencies=[Depends(api_auth)])
async def results(run_id:str,file_name:str):
    if file_name not in OUTPUT_FILES:raise HTTPException(404,'Unknown artifact name')
    row=store.get_run(run_id)
    if not row:raise HTTPException(404,'Unknown run')
    if store.IS_VERCEL:
        from vercel import blob
        try:
            result=await blob.get_blob(store.artifact_pathname(run_id,file_name),access='private')
        except blob.BlobNotFoundError:
            raise HTTPException(404,'Artifact unavailable') from None
        return Response(content=result.body,media_type='text/csv',headers={
            'Content-Disposition':f'attachment; filename="{file_name}"',
            'X-Content-Type-Options':'nosniff'})
    p=store.ROOT/'runs'/run_id/file_name
    if not p.is_file():raise HTTPException(404,'Artifact unavailable')
    return FileResponse(p,media_type='text/csv',filename=file_name)

@app.post('/runs/{run_id}/ack-file',dependencies=[Depends(api_auth)])
def ack_file(run_id:str,data:FileAcknowledgement):
    if data.file_name not in OUTPUT_FILES: raise HTTPException(422,'Unknown artifact')
    try:store.save_upload(run_id,data.file_name,data.drive_file_id)
    except ValueError as exc:raise HTTPException(409,str(exc))
    done=store.uploads(run_id)
    return {'run_id':run_id,'file_name':data.file_name,'acknowledged':True,
       'files_uploaded':len(done),'files_total':len(OUTPUT_FILES)}

@app.post('/runs/{run_id}/reserve-notification',dependencies=[Depends(api_auth)])
def reserve_notification(run_id:str):
    row=store.get_run(run_id)
    if not row:raise HTTPException(404,'Unknown run')
    try:send=store.reserve_send(run_id,OUTPUT_FILES)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    summary=json.loads(row['summary_json'])
    return {'run_id':run_id,'send':send,'status':'notification_reserved' if send else row['status'],
            'telegram_text':build_telegram(summary) if send else ''}

@app.post('/runs/{run_id}/complete',dependencies=[Depends(api_auth)])
def complete(run_id:str,receipt:TelegramReceipt):
    try:store.delivered(run_id,receipt.telegram_message_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    return {'run_id':run_id,'status':'delivered','telegram_message_id':receipt.telegram_message_id}

@app.get('/runs/{run_id}',dependencies=[Depends(api_auth)])
def get_run(run_id:str):
    row=store.get_run(run_id)
    if not row:raise HTTPException(404,'Unknown run')
    return {'run_id':run_id,'status':row['status'],'model_version':row['model_version'],
        'files_uploaded':store.uploads(run_id),'source_asof':row['as_of_date']}

@app.get('/history',dependencies=[Depends(api_auth)])
def get_history():return {'runs':store.history()}
