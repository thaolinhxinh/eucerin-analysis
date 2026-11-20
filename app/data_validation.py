"""Strict full-history CSV audit; no implicit zeros or unchecked future-day data."""
import io
import os
import numpy as np
import pandas as pd
from .forecast import get_assets

VERCEL_MAX_BYTES=4*1024*1024
MAX_BYTES=VERCEL_MAX_BYTES if os.getenv('VERCEL') == '1' else 20*1024*1024
REQUIRED={'product_id','dt','units_sold','title','is_eucerin'}


def validate_csv(raw):
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError(f'CSV empty or larger than {MAX_BYTES // (1024*1024)} MB')
    try:
        df=pd.read_csv(io.BytesIO(raw),dtype={'product_id':'string'},encoding='utf-8-sig',low_memory=False)
    except (ValueError,UnicodeDecodeError) as exc:
        raise ValueError('Cannot parse UTF-8 CSV') from exc
    absent=REQUIRED-set(df.columns)
    if absent: raise ValueError(f'Missing required columns: {sorted(absent)}')
    if df.empty: raise ValueError('CSV has no rows')
    if not df['is_eucerin'].astype(str).isin(['1','1.0','True','true']).all():
        raise ValueError('CSV contains non-confirmed Eucerin rows')
    df['ProductID']=df.product_id.astype('string').str.strip()
    df['Date']=pd.to_datetime(df.dt,format='%Y-%m-%d',errors='coerce')
    df['UnitsSold']=pd.to_numeric(df.units_sold,errors='coerce')
    df['Title']=df.title.fillna('').astype(str)
    invalid=(df.ProductID.isna()|(df.ProductID=='')|df.ProductID.str.endswith('.0',na=False)|
         df.Date.isna()|df.UnitsSold.isna()|~np.isfinite(df.UnitsSold.to_numpy(dtype=float))|
         (df.UnitsSold<0)|(df.UnitsSold%1!=0))
    if invalid.any(): raise ValueError(f'Invalid SKU/date/units rows: {int(invalid.sum())}')
    if df.duplicated(['ProductID','Date']).any(): raise ValueError('Duplicate SKU-date business key')
    df['GMV']=pd.to_numeric(df.gmv,errors='coerce') if 'gmv' in df.columns else np.nan
    df['IsHBGift']=df.Title.str.contains(r'\[HB GIFT\]',case=False,regex=True).astype(int)
    model,config,trained_ids,version=get_assets()
    start=pd.Timestamp(config['source_audit']['period_start'])
    last_train=pd.Timestamp(config['final_origin'])
    origin=df.Date.max()
    if origin<last_train: raise ValueError(f'Latest data {origin.date()} precedes trained-model cutoff {last_train.date()}')
    mode=os.getenv('APP_MODE','research').lower().strip()
    if mode not in ('research','production'):
        raise ValueError('APP_MODE must be research or production')
    if mode=='research' and origin != last_train:
        raise ValueError('Research mode locks source as-of date to 2026-10-12; switch APP_MODE=production for new observations')
    if origin>pd.Timestamp.today()+pd.Timedelta(days=1): raise ValueError('Source contains days later than current time')
    if df.Date.min()>start: raise ValueError('Cumulative source misses training-period start')
    if (origin-start).days>1095: raise ValueError('History >3 years requires feature/model review')
    unknown=set(df.ProductID.astype(str))-trained_ids
    panel=df[df.ProductID.astype(str).isin(trained_ids)].copy()
    missing_ids=trained_ids-set(panel.ProductID.astype(str))
    if missing_ids: raise ValueError(f'{len(missing_ids)} trained SKU histories missing; cannot infer full panel')
    required_dates=pd.date_range(start,origin,freq='D')
    for pid,g in panel.groupby('ProductID'):
        missing=required_dates.difference(pd.DatetimeIndex(g.Date))
        if len(missing): raise ValueError(f'SKU {pid} misses {len(missing)} observed days (first {missing[0].date()}); will NOT impute 0')
        if g.IsHBGift.nunique()!=1:raise ValueError(f'SKU {pid} changes HB GIFT flag')
    panel=panel.sort_values(['ProductID','Date']).reset_index(drop=True)
    positives=float((panel[panel.Date>=origin-pd.Timedelta(days=29)].UnitsSold>0).mean())
    base_rate=float(config['source_audit']['positive_rate_complete_panel'])
    warnings=[]
    if unknown: warnings.append(f'{len(unknown)} unknown SKU(s) not forecast: retraining required to include them')
    if abs(positives-base_rate)>=0.15:
        warnings.append(f'Occurrence-rate drift: last30={positives:.3f}, training={base_rate:.3f}')
    if (origin-last_train).days>30:
        warnings.append(f'Model is {(origin-last_train).days} days beyond last trained cutoff; out-of-time performance unverified')
    q99=panel[panel.Date<=last_train].UnitsSold.quantile(.99)
    anomalies=int((panel.UnitsSold>max(10,q99*10)).sum())
    if anomalies: warnings.append(f'{anomalies} unusually high SKU-days; verify campaigns/data quality')
    return panel,origin,{
        'source_rows':int(len(df)),'trained_skus':len(trained_ids),'unknown_skus':len(unknown),
        'source_skus':int(df.ProductID.nunique()),'panel_rows':int(len(panel)),
        'history_start':str(start.date()),'source_asof':str(origin.date()),
        'positive_rate_last_30d':positives,'reference_positive_rate':base_rate,'warnings':warnings,
        'source_has_gmv':'gmv' in df.columns}
