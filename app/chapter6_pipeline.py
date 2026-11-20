#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chapter 6 A/C: 7-day sale-occurrence classification and ADI-CV2 behavior.
No synthetic data, no future-value leakage. All features computed as of forecast origin.
Run: python chapter6_occurrence_behavior.py --input FILE.csv|.xlsx|.zip --output DIR
"""
import os, sys, csv, json, math, hashlib, argparse, zipfile, warnings, platform
from pathlib import Path
from datetime import timedelta
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import (f1_score, precision_score, recall_score, average_precision_score,
                             roc_auc_score, brier_score_loss, confusion_matrix, precision_recall_curve)
import joblib

V_ORIGINS = [pd.Timestamp('2026-09-14'),pd.Timestamp('2026-09-21'),pd.Timestamp('2026-09-28')]
TEST_ORIGIN = pd.Timestamp('2026-10-05')
FINAL_ORIGIN = pd.Timestamp('2026-10-12')
THRESHOLDS = np.round(np.arange(0.25,0.751,0.05),2)
RANDOM_STATE=42
NUM = ['Horizon','LastUnits','Lag1','Lag7','Lag14','Lag28','Sum7','Sum14','Sum30',
       'Freq7','Freq14','Freq30','Avg7','Avg14','Std7','DaysSinceSale',
       'ADIOrigin','CV2Origin','OriginPositiveDays','OriginObservedDays',
       'TargetWeekday','TargetMonth','TargetIsWeekend','IsHBGift']
CATS=['ProductID']
MODEL_NAMES=['Seasonal Naive','Historical Rate','Logistic Regression','Random Forest','Hist Gradient Boosting']


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def resolve_input(path):
    path=Path(path); assert path.exists(),f'Missing input: {path}'
    if path.suffix.lower() != '.zip': return path
    import tempfile
    tmp=Path(tempfile.mkdtemp(prefix='eucerin_ac_'))
    with zipfile.ZipFile(path) as z:
        # only allow safe names, limit uncompressed size
        items=[a for a in z.infolist() if not a.is_dir() and Path(a.filename).suffix.lower() in ('.csv','.xlsx')]
        if not items:raise ValueError('ZIP has no CSV or XLSX files')
        exact=[a for a in items if Path(a.filename).name.lower()=='historical_eucerin_confirmed.csv']
        if len(exact)!=1:
            raise ValueError('ZIP must contain exactly one historical_eucerin_confirmed.csv; do not guess which file is the Eucerin confirmed history')
        a=exact[0]
        if a.file_size>250*1024*1024:raise ValueError('ZIP input too large')
        out=tmp/Path(a.filename).name
        with z.open(a) as source,open(out,'wb') as dest:
            import shutil; shutil.copyfileobj(source,dest)
    return out


def load_audit(path, out):
    file=resolve_input(path)
    if file.suffix.lower()=='.csv': df=pd.read_csv(file,dtype={'product_id':'string'},low_memory=False,encoding='utf-8-sig')
    elif file.suffix.lower()=='.xlsx':
        workbook=pd.ExcelFile(file); choices=[]
        for sheet in workbook.sheet_names:
            t=pd.read_excel(file,sheet_name=sheet,nrows=2)
            if {'dt','units_sold','product_id'}.issubset(t.columns):choices.append(sheet)
        if len(choices)!=1:raise ValueError(f'Excel source must have exactly 1 sheet with dt,units_sold,product_id; found {choices}')
        df=pd.read_excel(file,sheet_name=choices[0],dtype={'product_id':'string'})
    else: raise ValueError('Use .csv, .xlsx, or .zip')
    print('Source:',file,'columns:',list(df.columns))
    mandatory={'dt','units_sold','product_id'}
    absent=mandatory-set(df.columns)
    if absent:raise ValueError(f'Missing required source columns {sorted(absent)}, no automatic meaning guessing permitted')
    if 'is_eucerin' in df.columns and not df['is_eucerin'].astype(str).isin(['1','1.0','True','true']).all():
        raise ValueError('The input contains non-Eucerin records. Provide the processed confirmed-Eucerin historical file; do not assume all brand matches are confirmed.')
    df=df.copy()
    df['ProductID']=df['product_id'].astype('string').str.strip()
    if df['ProductID'].str.endswith('.0',na=False).any():
        raise ValueError('Some ProductID have .0 suffix. Please verify original identifiers, do not silently coerce them.')
    df['Date']=pd.to_datetime(df['dt'],format='%Y-%m-%d',errors='coerce')
    df['UnitsSold']=pd.to_numeric(df['units_sold'],errors='coerce')
    bad=(df['Date'].isna()|df['ProductID'].isna()|(df['ProductID']=='')|df['UnitsSold'].isna()|(df['UnitsSold']<0)|(df['UnitsSold']%1!=0))
    dupe=df.duplicated(['ProductID','Date'],keep=False)
    if 'title' in df.columns:df['Title']=df['title'].fillna('').astype(str)
    else:df['Title']=''
    if 'gmv' in df.columns: df['GMV']=pd.to_numeric(df['gmv'],errors='coerce')
    else:df['GMV']=np.nan
    raw_start,raw_end=df['Date'].min(),df['Date'].max()
    if bad.any() or dupe.any():
        df.loc[bad|dupe,['product_id','dt','units_sold']].to_csv(out/'Invalid_Or_Duplicate_Records.csv',index=False,encoding='utf-8-sig')
        raise ValueError(f'Invalid records={int(bad.sum())}, duplicate SKU-date rows={int(dupe.sum())}; inspect Invalid_Or_Duplicate_Records.csv')
    if raw_end != FINAL_ORIGIN or raw_start!=pd.Timestamp('2026-07-15'):
        raise ValueError(f'Dataset dates {raw_start.date()}–{raw_end.date()} differ from locked evaluation protocol 2026-07-15–2026-10-12. Replan validation dates before rerunning.')
    days=(raw_end-raw_start).days+1
    per=df.groupby('ProductID').agg(ObservedDays=('Date','nunique'),UnitsTotal=('UnitsSold','sum'),GMVTotal=('GMV','sum'))
    complete=per[(per.ObservedDays==days)].index
    # Ensure true continuous coverage for each selected SKU
    part=df[df.ProductID.isin(complete)].copy()
    assert part.shape[0]==len(complete)*days
    assert all(g.Date.is_monotonic_increasing for _,g in part.sort_values('Date').groupby('ProductID',sort=False))
    part=part.sort_values(['ProductID','Date']).reset_index(drop=True)
    part['SaleOccurred']=(part.UnitsSold>0).astype(int)
    part['IsHBGift']=part.Title.str.contains(r'\[HB GIFT\]',regex=True,case=False).astype(int)
    if part.groupby('ProductID').IsHBGift.nunique().max()>1:raise ValueError('A SKU changes the HB GIFT label across days; review the label before using it as a feature')
    if 'gmv' in df.columns:
        per_gmv=part.GMV.sum()/df.GMV.sum() if df.GMV.sum()!=0 else np.nan
    else:per_gmv=np.nan
    audit=per.reset_index().rename(columns={'ProductID':'SKU'})
    audit['IsComplete']=audit.ObservedDays.eq(days)
    audit['MissingDays']=days-audit.ObservedDays
    audit['HasSale']=audit.UnitsTotal.gt(0)
    audit.to_csv(out/'Data_Audit.csv',index=False,encoding='utf-8-sig')
    summary={'source_name':file.name,'source_sha256':sha256(file),'source_rows':int(len(df)),
       'source_skus':int(per.shape[0]),'source_days':int(days),'period_start':str(raw_start.date()),
       'period_end':str(raw_end.date()),'source_duplicates':int(dupe.sum()),'source_invalid':int(bad.sum()),
       'complete_skus':int(len(complete)),'complete_rows':int(len(part)),
       'zeros_in_complete_panel':int((part.UnitsSold==0).sum()),
       'zero_rate_complete_panel':float((part.UnitsSold==0).mean()),
       'gmv_share_complete_panel':None if pd.isna(per_gmv) else float(per_gmv),
       'gift_skus_complete_panel':int(part[part.IsHBGift.eq(1)].ProductID.nunique()),
       'positive_rate_complete_panel':float(part.SaleOccurred.mean())}
    pd.DataFrame([summary]).to_csv(out/'Data_Audit_Summary.csv',index=False,encoding='utf-8-sig')
    print('Audit:',summary)
    if len(complete)<2:raise ValueError('Not enough complete SKU histories for classification')
    return part,summary


def behavior(y,asof,title='',product_id='',gift=0):
    y=np.asarray(y,dtype=float); n=len(y);p=y[y>0]; npos=len(p)
    sale_rate=npos/n if n else np.nan
    adi=n/npos if npos>0 else np.nan
    cv2=(np.std(p,ddof=0)/np.mean(p))**2 if npos>=2 and np.mean(p)>0 else np.nan
    if npos==0: group='No Sales'
    elif npos<2: group='Insufficient Positive Observations'
    elif adi<=1.32 and cv2<=0.49: group='Smooth'
    elif adi<=1.32 and cv2>0.49:group='Erratic'
    elif adi>1.32 and cv2<=0.49:group='Intermittent'
    else:group='Lumpy'
    return {'ProductID':str(product_id),'Title':title,'IsHBGift':int(gift),
            'ObservedDays':int(n),'PositiveDays':int(npos),'SaleRate':sale_rate,
            'UnitsTotal':float(y.sum()),'MeanPositiveUnits':float(p.mean()) if npos else np.nan,
            'ADI':float(adi) if np.isfinite(adi) else np.nan,
            'CV2':float(cv2) if np.isfinite(cv2) else np.nan,
            'BehaviorGroup':group}


def dim_behavior(panel,cutoff,outfile=None):
    rows=[]
    for id,g in panel[panel.Date.le(cutoff)].groupby('ProductID',sort=True):
        b=behavior(g.UnitsSold.values,cutoff,title=g.Title.iloc[-1],product_id=id,gift=g.IsHBGift.iloc[-1]);b['AsOfDate']=str(cutoff.date())
        b['GMVTotal']=float(g.GMV.sum()) if g.GMV.notna().any() else np.nan
        rows.append(b)
    res=pd.DataFrame(rows)
    if outfile:res.to_csv(outfile,index=False,encoding='utf-8-sig',float_format='%.8f')
    return res


def create_examples(panel):
    allrows=[]; bysku={}
    for pid,g in panel.groupby('ProductID',sort=True):
        g=g.sort_values('Date'); y=g.UnitsSold.to_numpy(dtype=float); ds=g.Date.to_numpy();
        bysku[pid]=g
        gift=int(g.IsHBGift.iloc[0]); n=len(y)
        for idx in range(29,n):
            history=y[:idx+1]; p=history[history>0]
            adi=len(history)/len(p) if len(p)>0 else np.nan
            cv2=(np.std(p,ddof=0)/p.mean())**2 if len(p)>1 else np.nan
            posidx=np.flatnonzero(history>0)
            ago=int(idx-posidx[-1]) if len(posidx) else len(history)
            row_base={'ProductID':str(pid),'OriginDate':pd.Timestamp(ds[idx]),'LastUnits':y[idx],
                'Lag1':y[idx-1], 'Lag7':y[idx-7], 'Lag14':y[idx-14],'Lag28':y[idx-28],
                'Sum7':sum(history[-7:]),'Sum14':sum(history[-14:]),'Sum30':sum(history[-30:]),
                'Freq7':float(np.mean(history[-7:]>0)),'Freq14':float(np.mean(history[-14:]>0)),
                'Freq30':float(np.mean(history[-30:]>0)), 'Avg7':float(np.mean(history[-7:])),
                'Avg14':float(np.mean(history[-14:])), 'Std7':float(np.std(history[-7:],ddof=0)),
                'DaysSinceSale':ago,'ADIOrigin':adi,'CV2Origin':cv2,
                'OriginPositiveDays':len(p),'OriginObservedDays':len(history),'IsHBGift':gift,
                'HistoricalRate':float(np.mean(history[-30:]>0))}
            for horizon in range(1,8):
                if idx+horizon >= n:continue
                tgt=pd.Timestamp(ds[idx+horizon]); row=row_base.copy()
                # target weekday and target-7 occurrence observed at origin or earlier
                row.update({'Horizon':horizon,'TargetDate':tgt,'TargetWeekday':tgt.weekday(),
                 'TargetMonth':tgt.month, 'TargetIsWeekend':int(tgt.weekday()>=5),
                 'SeasonalNaive':int(y[idx+horizon-7]>0),
                 'Target':int(y[idx+horizon]>0)})
                allrows.append(row)
    frame=pd.DataFrame(allrows)
    if frame.empty:raise ValueError('Not enough days to create 30-day trailing features plus 7-day horizon')
    assert (frame['OriginDate']<frame['TargetDate']).all()
    return frame


def features_from_origin(panel,asof):
    # Produces same feature contract as create_examples for unseen dates
    result=[]
    for pid,g in panel[panel.Date.le(asof)].groupby('ProductID',sort=True):
        g=g.sort_values('Date'); y=g.UnitsSold.to_numpy(dtype=float);ds=g.Date.to_numpy(); idx=len(y)-1
        if idx<29:raise ValueError(f'SKU {pid} has fewer than 30 observed days for forecast')
        p=y[y>0];adi=len(y)/len(p) if len(p) else np.nan
        cv2=(np.std(p,ddof=0)/p.mean())**2 if len(p)>1 else np.nan
        posidx=np.flatnonzero(y>0);ago=int(idx-posidx[-1]) if len(posidx) else len(y)
        b={'ProductID':str(pid),'OriginDate':asof,'LastUnits':y[idx],'Lag1':y[idx-1],
           'Lag7':y[idx-7], 'Lag14':y[idx-14], 'Lag28':y[idx-28],
           'Sum7':sum(y[-7:]), 'Sum14':sum(y[-14:]),'Sum30':sum(y[-30:]),
           'Freq7':float(np.mean(y[-7:]>0)),'Freq14':float(np.mean(y[-14:]>0)),
           'Freq30':float(np.mean(y[-30:]>0)), 'Avg7':np.mean(y[-7:]),
           'Avg14':np.mean(y[-14:]), 'Std7':np.std(y[-7:],ddof=0),
           'DaysSinceSale':ago,'ADIOrigin':adi,'CV2Origin':cv2,'OriginPositiveDays':len(p),
           'OriginObservedDays':len(y),'HistoricalRate':float(np.mean(y[-30:]>0)),
           'IsHBGift':int(g.IsHBGift.iloc[-1])}
        for h in range(1,8):
            target=asof+pd.Timedelta(days=h)
            row=b.copy();row.update({'Horizon':h,'TargetDate':target,'TargetWeekday':target.weekday(),
              'TargetMonth':target.month,'TargetIsWeekend':int(target.weekday()>=5),
              'SeasonalNaive':int(y[idx+h-7]>0)})
            result.append(row)
    return pd.DataFrame(result)


def make_models():
    prep_onehot=ColumnTransformer([
      ('num',Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=False)),('scaler',StandardScaler())]),NUM),
      ('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=True),CATS)],sparse_threshold=0.3)
    prep_rf=ColumnTransformer([
      ('num',SimpleImputer(strategy='median'),NUM),
      ('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATS)],sparse_threshold=0)
    prep_hist=ColumnTransformer([
      ('cat',OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=np.nan),CATS),
      ('num',SimpleImputer(strategy='median'),NUM)],sparse_threshold=0)
    return {
      'Logistic Regression':Pipeline([('prep',prep_onehot),('classifier',LogisticRegression(C=0.7,max_iter=500,random_state=RANDOM_STATE))]),
      'Random Forest':Pipeline([('prep',prep_rf),('classifier',RandomForestClassifier(n_estimators=110,max_depth=10,min_samples_leaf=12,n_jobs=-1,random_state=RANDOM_STATE))]),
      'Hist Gradient Boosting':Pipeline([('prep',prep_hist),('classifier',HistGradientBoostingClassifier(max_iter=110,max_leaf_nodes=15,learning_rate=0.07,l2_regularization=3, categorical_features=[0],random_state=RANDOM_STATE))])
    }


def calc_metrics(y,p,thresh=0.5):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    pred=(p>=thresh).astype(int)
    if len(y)==0:return {}
    tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return dict(N=int(len(y)),PositiveRate=float(y.mean()),Threshold=float(thresh),
      F1=float(f1_score(y,pred,zero_division=0)),
      MacroF1=float(f1_score(y,pred,average='macro',zero_division=0)),
      Precision=float(precision_score(y,pred,zero_division=0)),
      Recall=float(recall_score(y,pred,zero_division=0)),
      AveragePrecision=float(average_precision_score(y,p)) if np.any(y) else np.nan,
      ROCAUC=float(roc_auc_score(y,p)) if len(np.unique(y))==2 else np.nan,
      Brier=float(brier_score_loss(y,p)),TP=int(tp),TN=int(tn),FP=int(fp),FN=int(fn))


def baseline_prob(df,model):
    if model=='Seasonal Naive':return df.SeasonalNaive.to_numpy(dtype=float)
    if model=='Historical Rate':return df.HistoricalRate.to_numpy(dtype=float)
    raise ValueError(model)


def val_process(examples,output,enable_lightgbm=True):
    models=make_models()
    if enable_lightgbm:
        try:
            from lightgbm import LGBMClassifier
            prep=ColumnTransformer([('cat',OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=-1),CATS),('num',SimpleImputer(strategy='median'),NUM)],sparse_threshold=0)
            models['LightGBM']=Pipeline([('prep',prep),('classifier',LGBMClassifier(n_estimators=160,learning_rate=0.04,num_leaves=12,min_child_samples=35,reg_lambda=5,verbosity=-1,n_jobs=2,random_state=RANDOM_STATE))])
        except Exception as e:
            print('LightGBM skipped:',repr(e))
    names=['Seasonal Naive','Historical Rate']+list(models)
    val_parts=[]; fit_logs=[]
    for fold,origin in enumerate(V_ORIGINS,1):
        train=examples[examples.TargetDate.le(origin)]
        val=examples[examples.OriginDate.eq(origin)]
        assert train.TargetDate.max()<=origin and val.TargetDate.min()>origin
        if len(val)==0:raise ValueError(f'Validation origin {origin} absent in data')
        print(f'V{fold}: train {len(train):,}, validation {len(val):,}, date {origin.date()}',flush=True)
        fit_logs.append({'Fold':f'V{fold}','Origin':str(origin.date()),'TrainRows':int(len(train)),'ValRows':int(len(val)),
                        'MaxTrainLabelDate':str(train.TargetDate.max().date())})
        for name in names:
            if name in models:
                m=clone(models[name]);m.fit(train[NUM+CATS],train.Target)
                proba=m.predict_proba(val[NUM+CATS])[:,1]
            else:proba=baseline_prob(val,name)
            tab=val[['ProductID','OriginDate','TargetDate','Horizon','Target','IsHBGift']].copy()
            tab['Fold']=f'V{fold}';tab['Model']=name;tab['Probability']=np.clip(proba,0,1)
            val_parts.append(tab)
    va=pd.concat(val_parts,ignore_index=True)
    records=[]
    for name in names:
        tab=va[va.Model==name]
        for th in THRESHOLDS:
            fold_score=[f1_score(f.Target,f.Probability.ge(th).astype(int),zero_division=0) for _,f in tab.groupby('Fold')]
            m=calc_metrics(tab.Target,tab.Probability,th)
            records.append({'Model':name,'Threshold':float(th),'MeanFoldF1':float(np.mean(fold_score)),
                            'StdFoldF1':float(np.std(fold_score,ddof=0)),'PooledAP':m['AveragePrecision'],
                            'PooledBrier':m['Brier']})
    grid=pd.DataFrame(records).sort_values(['MeanFoldF1','StdFoldF1','PooledAP','PooledBrier'],ascending=[False,True,False,True])
    selected_each=(grid.sort_values(['MeanFoldF1','StdFoldF1','PooledAP','PooledBrier'],ascending=[False,True,False,True]).drop_duplicates('Model'))
    selected=selected_each.iloc[0]
    thresh_by={r.Model:float(r.Threshold) for r in selected_each.itertuples()}
    rows=[]
    for name in names:
        for fold in ['V1','V2','V3']:
            t=va[(va.Model==name)&(va.Fold==fold)]
            rows.append({'Model':name,'Fold':fold,**calc_metrics(t.Target,t.Probability,thresh_by[name])})
        t=va[va.Model==name]
        rows.append({'Model':name,'Fold':'VAL_POOLED',**calc_metrics(t.Target,t.Probability,thresh_by[name])})
    pd.DataFrame(rows).to_csv(output/'Validation_Metrics.csv',index=False,encoding='utf-8-sig')
    selected_each.to_csv(output/'Model_Selection_Validation.csv',index=False,encoding='utf-8-sig')
    va.to_csv(output/'Validation_Predictions_All.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(fit_logs).to_csv(output/'Temporal_Split_Audit.csv',index=False,encoding='utf-8-sig')
    print('SELECTED:',selected['Model'],'threshold',selected['Threshold'],'val MeanFoldF1',selected['MeanFoldF1'],flush=True)
    return models, str(selected['Model']),float(selected['Threshold']),va,selected_each


def predict_one(name,models,examples,origin,asof=None):
    train=examples[examples.TargetDate.le(origin)]
    hold=examples[examples.OriginDate.eq(origin)]
    if hold.empty:raise ValueError('No true labeled rows for test')
    if name in models:
        m=clone(models[name]);m.fit(train[NUM+CATS],train.Target)
        p=m.predict_proba(hold[NUM+CATS])[:,1]
    else:m=None;p=baseline_prob(hold,name)
    return m,hold.copy(),np.clip(p,0,1)


def output_holdout(examples,panel,models,chosen,threshold,output):
    m,hold,p=predict_one(chosen,models,examples,TEST_ORIGIN)
    beh=dim_behavior(panel,TEST_ORIGIN)
    lookup=beh.set_index('ProductID')['BehaviorGroup']
    hold['BehaviorGroup']=hold.ProductID.map(lookup)
    hold['ProbabilityOfSale']=p
    hold['PredictedSaleFlag']=(p>=threshold).astype(int)
    hold['DecisionThreshold']=threshold
    hold['ModelName']=chosen
    hold['ActualSaleFlag']=hold.Target.astype(int)
    hold['Correct']=hold.ActualSaleFlag.eq(hold.PredictedSaleFlag)
    keep=['ProductID','OriginDate','TargetDate','Horizon','ActualSaleFlag','ProbabilityOfSale','PredictedSaleFlag','DecisionThreshold','IsHBGift','BehaviorGroup','ModelName','Correct']
    hold[keep].to_csv(output/'Holdout_Predictions.csv',index=False,encoding='utf-8-sig')
    overall=calc_metrics(hold.Target,p,threshold)
    pd.DataFrame([{'Model':chosen,'Cutoff':TEST_ORIGIN.date(),'HoldoutStart':str((TEST_ORIGIN+pd.Timedelta(days=1)).date()),'HoldoutEnd':'2026-10-12',**overall}]).to_csv(output/'Holdout_Metrics.csv',index=False,encoding='utf-8-sig')
    group_rows=[]
    for grp,g in hold.groupby('BehaviorGroup'):
        group_rows.append({'Group':grp,**calc_metrics(g.Target,g.ProbabilityOfSale,threshold)})
    pd.DataFrame(group_rows).to_csv(output/'Holdout_By_Behavior.csv',index=False,encoding='utf-8-sig')
    hbrows=[{'IsHBGift':int(gift),**calc_metrics(g.Target,g.ProbabilityOfSale,threshold)} for gift,g in hold.groupby('IsHBGift')]
    pd.DataFrame(hbrows).to_csv(output/'Holdout_By_HBGift.csv',index=False,encoding='utf-8-sig')
    horizon_rows=[{'Horizon':int(h),**calc_metrics(g.Target,g.ProbabilityOfSale,threshold)} for h,g in hold.groupby('Horizon')]
    pd.DataFrame(horizon_rows).to_csv(output/'Holdout_By_Horizon.csv',index=False,encoding='utf-8-sig')
    sku_err=(hold.groupby('ProductID').agg(Misclassified=('Correct',lambda z:int((~z).sum())),ActualSaleDays=('ActualSaleFlag','sum'),PredictedSaleDays=('PredictedSaleFlag','sum'),IsHBGift=('IsHBGift','max'),BehaviorGroup=('BehaviorGroup','first'))
             .sort_values(['Misclassified','ProductID'],ascending=[False,True]))
    sku_err.to_csv(output/'Holdout_Misclassified_SKU.csv',encoding='utf-8-sig')
    # Holdout comparisons: every model evaluated without reselecting after seeing results
    comps=[]
    for name in ['Seasonal Naive','Historical Rate']+list(models):
        _m,_h,_p=predict_one(name,models,examples,TEST_ORIGIN)
        # threshold fixed for name from validation separately (read csv)
        tmap=pd.read_csv(output/'Model_Selection_Validation.csv').set_index('Model')['Threshold']
        th=float(tmap[name])
        comps.append({'Model':name,**calc_metrics(_h.Target,_p,th)})
    pd.DataFrame(comps).to_csv(output/'Holdout_Model_Comparison_Descriptive.csv',index=False,encoding='utf-8-sig')
    print('HOLDOUT:',overall,flush=True)
    return hold,overall


def final_forecast(examples,panel,models,chosen,threshold,out):
    tr=examples[examples.TargetDate.le(FINAL_ORIGIN)]
    future=features_from_origin(panel,FINAL_ORIGIN)
    assert len(future)==7*panel.ProductID.nunique()
    if chosen in models:
        model=clone(models[chosen]);model.fit(tr[NUM+CATS],tr.Target)
        p=model.predict_proba(future[NUM+CATS])[:,1]
    else:
        model=None;p=baseline_prob(future,chosen)
    groups=dim_behavior(panel,FINAL_ORIGIN,out/'DimSKU_Behavior.csv')
    lookup=groups.set_index('ProductID')
    future['ProbabilityOfSale']=np.clip(p,0,1)
    future['PredictedSaleFlag']=(future.ProbabilityOfSale>=threshold).astype(int)
    future['DecisionThreshold']=threshold
    future['BehaviorGroup']=future.ProductID.map(lookup.BehaviorGroup)
    future['Title']=future.ProductID.map(lookup.Title)
    future['ModelName']=chosen
    future['ForecastOrigin']=str(FINAL_ORIGIN.date())
    future=future.rename(columns={'TargetDate':'ForecastDate'})
    keep=['ProductID','Title','ForecastDate','Horizon','ProbabilityOfSale','PredictedSaleFlag',
          'DecisionThreshold','BehaviorGroup','IsHBGift','ForecastOrigin','ModelName']
    final=future[keep]
    assert not final.duplicated(['ProductID','ForecastDate']).any()
    assert final.ProbabilityOfSale.between(0,1).all()
    assert final.ForecastDate.min()==pd.Timestamp('2026-10-13') and final.ForecastDate.max()==pd.Timestamp('2026-10-19')
    final.to_csv(out/'FactOccurrenceForecast_PowerBI.csv',index=False,encoding='utf-8-sig',float_format='%.6f')
    if model is not None:joblib.dump(model,out/'Model_Classification.joblib')
    else:joblib.dump({'Baseline':chosen,'Threshold':threshold,'FeatureSchema':NUM+CATS},out/'Model_Classification.joblib')
    return groups,final


def charts(panel,audit,dim,va,hold,final,out):
    img=out/'Chapter6_Charts';img.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'figure.dpi':140,'axes.spines.top':False,'axes.spines.right':False})
    def save(n):plt.tight_layout();plt.savefig(img/n,dpi=175,bbox_inches='tight',facecolor='white');plt.close()
    # 1 panel count distribution
    cov=pd.read_csv(out/'Data_Audit.csv');plt.figure(figsize=(8,4));plt.hist(cov.ObservedDays,bins=np.arange(0,99,5),edgecolor='white');plt.title('Observed-day coverage across Eucerin SKUs');plt.xlabel('Observed days');plt.ylabel('SKU count');save('Figure_6_01_Coverage.png')
    # 2 daily occurrence rate
    t=panel.groupby('Date').SaleOccurred.agg(['mean','sum']).reset_index();plt.figure(figsize=(10,4));plt.plot(t.Date,t['mean']);plt.ylim(0,1);plt.title('Daily sale-occurrence rate: complete-SKU panel');plt.ylabel('Fraction of SKUs with sales');save('Figure_6_02_Daily_Occurrence.png')
    # 3 group counts
    order=['Smooth','Erratic','Intermittent','Lumpy','No Sales','Insufficient Positive Observations'];c=dim.BehaviorGroup.value_counts().reindex(order,fill_value=0);plt.figure(figsize=(9,4));plt.barh(c.index[::-1],c.values[::-1]);plt.xlabel('Number of SKUs');plt.title('SKU behavior groups (ADI and CV²)');save('Figure_6_03_Behavior_Counts.png')
    # 4 Scatter
    plt.figure(figsize=(7,5));t=dim.dropna(subset=['ADI','CV2'])
    for grp,z in t.groupby('BehaviorGroup'):plt.scatter(z.ADI,z.CV2,label=grp,s=36,alpha=.75)
    plt.axvline(1.32,ls='--',lw=1);plt.axhline(.49,ls='--',lw=1);plt.xlabel('Average Demand Interval (ADI)');plt.ylabel('Squared coefficient of variation (CV²)');plt.title('Behavior segmentation by SKU');plt.legend(fontsize=8);save('Figure_6_04_ADI_CV2_Scatter.png')
    # 5 group units
    gg=dim.groupby('BehaviorGroup').UnitsTotal.sum().sort_values(ascending=False);plt.figure(figsize=(9,4));plt.bar(gg.index,gg.values);plt.xticks(rotation=15,ha='right');plt.ylabel('Recorded Units Sold');plt.title('Units contribution by behavior group');save('Figure_6_05_Units_By_Group.png')
    # 6 Validation F1
    v=pd.read_csv(out/'Validation_Metrics.csv');v=v[v.Fold.eq('VAL_POOLED')].sort_values('F1');plt.figure(figsize=(9,4));plt.barh(v.Model,v.F1);plt.xlim(0,1);plt.xlabel('Pooled validation F1');plt.title('Model comparison on validation folds');save('Figure_6_06_Validation_F1.png')
    # 7 confusion
    cm=confusion_matrix(hold.ActualSaleFlag,hold.PredictedSaleFlag,labels=[0,1]);fig,ax=plt.subplots(figsize=(5.5,4.6));h=ax.imshow(cm,cmap='Blues');plt.colorbar(h,ax=ax)
    for i in range(2):
        for j in range(2):ax.text(j,i,str(cm[i,j]),ha='center',va='center',fontsize=16)
    ax.set_xticks([0,1],['Pred no-sale','Pred sale']);ax.set_yticks([0,1],['Actual no-sale','Actual sale']);ax.set_title('Holdout confusion matrix');save('Figure_6_07_Holdout_Confusion.png')
    # 8 PR
    from sklearn.metrics import precision_recall_curve
    pp,rr,_=precision_recall_curve(hold.ActualSaleFlag,hold.ProbabilityOfSale)
    plt.figure(figsize=(7,4.5));plt.plot(rr,pp);plt.xlabel('Recall');plt.ylabel('Precision');plt.title('Holdout precision–recall curve');save('Figure_6_08_Holdout_PR.png')
    # 9 Calibration
    pr=hold.ProbabilityOfSale.to_numpy(); ys=hold.ActualSaleFlag.to_numpy(); edges=np.linspace(0,1,11); bins=np.minimum(np.digitize(pr,edges,right=True)-1,9); bins=np.maximum(bins,0)
    b=[]
    for i in range(10):
        m=bins==i
        if m.any():b.append((pr[m].mean(),ys[m].mean(),m.sum()))
    plt.figure(figsize=(6,4.5));plt.plot([0,1],[0,1],'--',color='gray',label='Perfect calibration');plt.plot([x[0] for x in b],[x[1] for x in b],marker='o',label='Observed');plt.legend();plt.xlim(0,1);plt.ylim(0,1);plt.xlabel('Predicted probability');plt.ylabel('Observed sale frequency');plt.title('Holdout calibration by probability bin');save('Figure_6_09_Holdout_Calibration.png')
    # 10 F1 by horizon
    h=pd.read_csv(out/'Holdout_By_Horizon.csv');plt.figure(figsize=(7,4));plt.plot(h.Horizon,h.F1,marker='o');plt.ylim(0,1);plt.xlabel('Forecast horizon (days)');plt.ylabel('F1 score');plt.title('Holdout F1 by forecast horizon');save('Figure_6_10_Horizon_F1.png')
    # 11 daily expected SKU occurrences sum probabilities -- NOT units
    tt=final.groupby('ForecastDate').agg(ExpectedSellingSKUs=('ProbabilityOfSale','sum'),FlaggedSKUs=('PredictedSaleFlag','sum')).reset_index()
    plt.figure(figsize=(8,4));plt.bar(pd.to_datetime(tt.ForecastDate).dt.strftime('%m-%d'),tt.ExpectedSellingSKUs);plt.ylabel('Sum of probabilities (expected selling SKUs)');plt.xlabel('Forecast date, 2026');plt.title('Expected number of selling SKUs (not Units Sold)');save('Figure_6_11_Occurrence_Forecast.png')
    return tt


def docs(out,summary,dim,chosen,threshold,hold,overall,forecast):
    version={'python':platform.python_version(),'pandas':pd.__version__,'sklearn':__import__('sklearn').__version__}
    try:version['lightgbm']=__import__('lightgbm').__version__
    except:version['lightgbm']='not installed'
    config={'task':'Binary sale occurrence T+1..T+7','segment':'ADI-CV2 descriptive, no target leakage',
      'observed_window':'2026-07-15 to 2026-10-12','validation_origins':[str(x.date()) for x in V_ORIGINS],
      'holdout_origin':'2026-10-05','final_origin':'2026-10-12',
      'selected_model':chosen,'threshold':threshold,'feature_columns':NUM+CATS,
      'positive_target':'UnitsSold > 0','cv2_ddof':0,'threshold_selection':'mean validation fold F1',
      'zero_missing_policy':'No missing dates filled; complete SKU 90-day panel only',
      'versions':version,'source_audit':summary}
    with open(out/'Model_Config.json','w',encoding='utf8') as f:json.dump(config,f,ensure_ascii=False,indent=2,default=str)
    groups=dim.BehaviorGroup.value_counts().to_dict();rows=len(forecast); predicted=int(forecast.PredictedSaleFlag.sum());exp=float(forecast.ProbabilityOfSale.sum())
    txt=f'''# CHƯƠNG 6 – PHƯƠNG PHÁP\n\nTập Eucerin đã xác nhận: {summary['source_rows']:,} bản ghi của {summary['source_skus']} SKU. Chọn {summary['complete_skus']} SKU đủ 90 ngày ({summary['complete_rows']:,} SKU–ngày); không gán 0 cho ngày thiếu. Tỷ lệ không bán: {summary['zero_rate_complete_panel']*100:.2f}%.\n\n**A – Binary sale occurrence**: nhãn 1 khi `UnitsSold > 0`; xác suất 7 ngày theo mỗi SKU, không dự báo số lượng bán hay GMV. Đặc trưng được tính tại forecast origin, không dùng đơn vị bán của các ngày sau origin. Các fold 14/09, 21/09, 28/09 được dùng để chọn mô hình và ngưỡng theo F1 trung bình; test 05/10 chỉ dùng một lần để đo lường.\n\n**C – Segmentation**: ADI = số ngày quan sát/số ngày có bán. CV² = (độ lệch chuẩn tổng thể trên ngày bán dương/trung bình ngày bán dương)². Smooth/Erratic/Intermittent/Lumpy theo ngưỡng ADI 1,32 và CV² 0,49. SKU có ít hơn hai ngày bán dương có nhóm riêng. Group tại 05/10 dùng để phân tích holdout; group tại 12/10 dùng cho dự báo, không dùng group toàn bộ lịch sử làm feature train.\n\n**Các metric**: Precision, Recall, F1-positive, macro-F1, Average Precision, ROC-AUC và Brier; confusion matrix và calibration.\n\n**Nguồn hạn chế**: Chỉ có chỉ số bên thứ ba; ngày có UnitsSold=0 là không bán theo cách ghi nhận của nguồn, không thể khẳng định không có nhu cầu thực tế.\n'''
    (out/'Chapter6_Methodology.md').write_text(txt,encoding='utf8')
    rs=f'''# KẾT QUẢ THỰC NGHIỆM – DỰ BÁO XÁC SUẤT CÓ BÁN\n\n- Dataset: **{summary['complete_skus']} SKU / {summary['complete_rows']:,} quan sát**; zero rate **{summary['zero_rate_complete_panel']:.2%}**; GMV coverage **{summary['gmv_share_complete_panel']:.2%}**.\n- ADI/CV² groups: {groups}.\n- Mô hình được chọn từ **3 validation folds**: **{chosen}**, threshold **{threshold:.2f}**.\n- Holdout 06–12/10: N={overall['N']}, F1={overall['F1']:.4f}, macro-F1={overall['MacroF1']:.4f}, Precision={overall['Precision']:.4f}, Recall={overall['Recall']:.4f}, AP={overall['AveragePrecision']:.4f}, ROC-AUC={overall['ROCAUC']:.4f}, Brier={overall['Brier']:.4f}.\n- Dự báo hồi cứu 13–19/10: **{rows} SKU–ngày**, {predicted} nhãn có bán dự báo, **tổng xác suất {exp:.2f}**, hiểu là số SKU–ngày kỳ vọng có bán, không phải số sản phẩm bán.\n- Không thay mô hình dựa trên holdout. Đọc `Validation_Metrics.csv`, `Holdout_By_Behavior.csv`, `Holdout_By_Horizon.csv` để phân tích khác biệt theo nhóm.\n- Nhóm HB GIFT được gắn nhãn qua tên sản phẩm, chỉ mô tả, không xác nhận chương trình khuyến mãi/đơn tặng thực tế.\n'''
    (out/'Chapter6_Results_Summary.md').write_text(rs,encoding='utf8')
    return config


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',default='/content/chapter6_outputs')
    parser.add_argument('--no-lightgbm',action='store_true')
    args=parser.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    panel,summary=load_audit(args.input,out)
    dim=dim_behavior(panel,FINAL_ORIGIN,out/'DimSKU_Behavior.csv')
    ex=create_examples(panel)
    print('TRAIN EXAMPLES',len(ex),'per validation horizon',flush=True)
    models,chosen,th,val,select=val_process(ex,out,enable_lightgbm=not args.no_lightgbm)
    hold,overall=output_holdout(ex,panel,models,chosen,th,out)
    dim,forecast=final_forecast(ex,panel,models,chosen,th,out)
    # Direct no-leakage test: changing future observed sales must not change features at cutoff.
    f0=features_from_origin(panel,TEST_ORIGIN).sort_values(['ProductID','Horizon']).reset_index(drop=True)
    edited=panel.copy(); edited.loc[edited.Date.gt(TEST_ORIGIN),'UnitsSold']=999999
    f1=features_from_origin(edited,TEST_ORIGIN).sort_values(['ProductID','Horizon']).reset_index(drop=True)
    checkcols=['ProductID']+NUM+['HistoricalRate','SeasonalNaive','TargetDate']
    import pandas.testing as pdt
    pdt.assert_frame_equal(f0[checkcols],f1[checkcols],check_dtype=True)
    (out/'No_Future_Leakage_Test.txt').write_text('PASS: Mutating all observed values after 2026-10-05 does not change 7-day forecast features at the origin.\n',encoding='utf-8')
    dates=pd.date_range('2026-07-15','2026-10-19',freq='D')
    cal=pd.DataFrame({'Date':dates});cal['Year']=cal.Date.dt.year;cal['Month']=cal.Date.dt.month;cal['YearMonth']=cal.Date.dt.strftime('%Y-%m');cal['Quarter']='Q'+cal.Date.dt.quarter.astype(str);cal['ISOWeek']=cal.Date.dt.isocalendar().week.astype(int);cal['WeekdayNumber']=cal.Date.dt.isocalendar().day.astype(int);cal['WeekdayName']=cal.Date.dt.day_name()
    cal.to_csv(out/'DimDate_Extended_For_PowerBI.csv',index=False,encoding='utf-8-sig')
    expected=charts(panel,summary,dim,val,hold,forecast,out)
    expected.to_csv(out/'Forecast_Daily_Summary.csv',index=False,encoding='utf-8-sig')
    conf=docs(out,summary,dim,chosen,th,hold,overall,forecast)
    print('OUTPUT',out,'selection',chosen,'threshold',th,'F1',overall['F1'],'forecast rows',len(forecast),flush=True)
    return out

if __name__=='__main__':main()
