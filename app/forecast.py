"""Load trusted frozen model only; never joblib.load an uploaded file."""
import hashlib, json, os
from functools import lru_cache
from pathlib import Path
import numpy as np
from fastapi import HTTPException
from .features import NUM,CATS,FEATURE_COLUMNS,features_from_origin

BASE=Path(__file__).resolve().parent.parent
MODEL_DIR=Path(os.getenv('MODEL_DIR',str(BASE/'models')))

@lru_cache(maxsize=1)
def get_assets():
    mod=MODEL_DIR/'Model_Classification.joblib'
    cfg=MODEL_DIR/'Model_Config.json'
    if not mod.is_file() or not cfg.is_file():
        raise RuntimeError('Trained model/config missing')
    import joblib
    model=joblib.load(mod)
    info=json.loads(cfg.read_text(encoding='utf-8'))
    if info.get('feature_columns')!=FEATURE_COLUMNS:
        raise RuntimeError('Model_Config feature order disagrees with training code')
    if not hasattr(model,'predict_proba'):
        raise RuntimeError('Trained asset does not implement predict_proba')
    if not 0 < float(info['threshold']) < 1:
        raise RuntimeError('Threshold invalid')
    version=hashlib.sha256(mod.read_bytes()+cfg.read_bytes()).hexdigest()[:16]
    try:
        cats=model.named_steps['prep'].named_transformers_['cat'].categories_
        ids={str(v) for v in cats[0]}
    except Exception as exc:
        raise RuntimeError('Cannot read trained SKU vocabulary from model pipeline') from exc
    return model,info,ids,version


def forecast(panel,origin):
    model,conf,ids,version=get_assets()
    x=features_from_origin(panel,origin)
    if set(x.ProductID.astype(str))!=ids or len(x)!=7*len(ids):
        raise ValueError('Forecast sample count/vocabulary disagrees with trained SKU panel')
    probabilities=np.asarray(model.predict_proba(x[FEATURE_COLUMNS])[:,1],dtype=float)
    if not np.isfinite(probabilities).all() or np.any((probabilities<0)|(probabilities>1)):
        raise ValueError('Invalid model probabilities')
    x['ProbabilityOfSale']=probabilities
    x['PredictedSaleFlag']=(probabilities>=float(conf['threshold'])).astype('int64')
    x['DecisionThreshold']=float(conf['threshold'])
    return x,conf,version
