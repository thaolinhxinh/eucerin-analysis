"""Produce Power BI-ready CSVs; probabilities are never treated as units."""
from pathlib import Path
import pandas as pd
import numpy as np
from .segmentation import segment

OUTPUT_FILES=(
 'FactOccurrenceForecast_PowerBI.csv','DimSKU_Behavior.csv',
 'DimDate_Extended_For_Forecast.csv','Model_Validation_Metrics.csv',
 'Model_Holdout_Metrics.csv','Model_Run_History.csv',
 'Monitoring_Daily_PowerBI.csv','SKU_Monitoring_Alerts.csv',
)

def make_outputs(panel,origin,features,config,model_version,run_id,directory,diagnostics,reference):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    dim=segment(panel,origin)
    lookup=dim.set_index('ProductID')
    out=features.rename(columns={'TargetDate':'ForecastDate'})[[
      'ProductID','ForecastDate','Horizon','ProbabilityOfSale','PredictedSaleFlag','DecisionThreshold']].copy()
    out['ForecastDate']=pd.to_datetime(out.ForecastDate).dt.strftime('%Y-%m-%d')
    out['ForecastOrigin']=str(origin.date())
    out['BehaviorGroup']=out.ProductID.map(lookup.BehaviorGroup)
    out['ModelVersion']=model_version
    out['RunID']=run_id
    out['RunSKUKey']=out['RunID'].astype(str)+'|'+out['ProductID'].astype(str)
    out['Title']=out.ProductID.map(lookup.Title)
    if out[['ProbabilityOfSale']].isna().any().any() or not out.ProbabilityOfSale.between(0,1).all():
        raise ValueError('NaN or invalid forecast probability')
    if out.duplicated(['RunID','ProductID','ForecastDate']).any():
        raise ValueError('Duplicate RunID/SKU/ForecastDate')
    if len(out)!=7*dim.ProductID.nunique():
        raise ValueError('Forecast scope mismatch')
    dim['ModelVersion']=model_version;dim['RunID']=run_id
    dim['ForecastOrigin']=str(origin.date())
    dim['RunSKUKey']=dim['RunID'].astype(str)+'|'+dim['ProductID'].astype(str)
    # each probabilistic estimate is one SKU-day, not a number of units sold
    daily=out.groupby('ForecastDate').agg(
      ExpectedSellingSKUs=('ProbabilityOfSale','sum'),
      PredictedSellingSKUFlags=('PredictedSaleFlag','sum'),
      SKUs=('ProductID','nunique')).reset_index()
    daily['RunID']=run_id;daily['ModelVersion']=model_version
    sku=out.groupby('ProductID').agg(MeanForecastProbability=('ProbabilityOfSale','mean'),
            PredictedSaleDays=('PredictedSaleFlag','sum')).reset_index()
    monitoring=dim.merge(sku,on='ProductID',validate='one_to_one')
    monitoring['DeltaHistoricalVsForecast']=monitoring.SaleRate-monitoring.MeanForecastProbability
    alerts=monitoring[(monitoring.SaleRate>=.5)&(monitoring.DeltaHistoricalVsForecast>=.3)].copy()
    alerts=alerts.sort_values('DeltaHistoricalVsForecast',ascending=False)
    alerts['AlertType']='Forecast lower than observed positive-day frequency; review only'
    dates=pd.date_range(panel.Date.min(), origin+pd.Timedelta(days=7),freq='D')
    cal=pd.DataFrame({'Date':dates.strftime('%Y-%m-%d')})
    cal['Year']=dates.year;cal['Month']=dates.month
    cal['YearMonth']=dates.strftime('%Y-%m')
    cal['ISOWeek']=dates.isocalendar().week.to_numpy(dtype=int)
    cal['WeekdayIndex']=dates.weekday
    cal['IsForecast']=dates>origin
    def save(df,name):
        df.to_csv(directory/name,index=False,encoding='utf-8-sig',float_format='%.8f')
    save(out,'FactOccurrenceForecast_PowerBI.csv')
    save(dim,'DimSKU_Behavior.csv')
    save(cal,'DimDate_Extended_For_Forecast.csv')
    for old,new in [('Validation_Metrics.csv','Model_Validation_Metrics.csv'),
                    ('Holdout_Metrics.csv','Model_Holdout_Metrics.csv')]:
        metrics=pd.read_csv(Path(reference)/old)
        metrics['ModelVersion']=model_version
        metrics['EvaluationPeriod']='2026-09 / validation' if old.startswith('Validation') else '2026-10-06 to 2026-10-12 / holdout'
        save(metrics,new)
    save(daily,'Monitoring_Daily_PowerBI.csv')
    save(alerts,'SKU_Monitoring_Alerts.csv')
    summary={'run_id':run_id,'model_version':model_version,'as_of_date':str(origin.date()),
     'forecast_start':str((origin+pd.Timedelta(days=1)).date()),
     'forecast_end':str((origin+pd.Timedelta(days=7)).date()),
     'trained_skus':int(dim.ProductID.nunique()),'forecast_rows':int(len(out)),
     'expected_sale_sku_days':round(float(out.ProbabilityOfSale.sum()),6),
     'predicted_sale_sku_days':int(out.PredictedSaleFlag.sum()),
     'threshold':float(config['threshold']),
     'behavior_counts':{str(k):int(v) for k,v in dim.BehaviorGroup.value_counts().items()},
     'daily':[{'ForecastDate':str(x.ForecastDate),'ExpectedSellingSKUs':round(float(x.ExpectedSellingSKUs),4),
               'PredictedSellingSKUFlags':int(x.PredictedSellingSKUFlags)} for x in daily.itertuples()],
     'alert_count':len(alerts),
     'alerts':[{'sku':str(x.ProductID),'title':str(x.Title),
               'behavior_group':str(x.BehaviorGroup),
               'historical_sale_rate':round(float(x.SaleRate),4),
               'mean_forecast_sale_probability':round(float(x.MeanForecastProbability),4),
               'difference':round(float(x.DeltaHistoricalVsForecast),4)} for x in alerts.head(5).itertuples()],
     'warnings':diagnostics['warnings'],
     'source_rows':diagnostics['source_rows'],
     'excluded_untrained_skus':diagnostics['unknown_skus'],
     'explanation':'Sum of probabilities is expected SKU-days with recorded sales, never Units Sold / GMV'}
    return summary


def build_telegram(summary):
    lines=['📊 EUCERIN · BÁO CÁO DỰ BÁO KHẢ NĂNG BÁN',
       f"Ngày chốt: {summary['as_of_date']}",
       f"Kỳ dự báo: {summary['forecast_start']} → {summary['forecast_end']}",
       f"Phạm vi: {summary['trained_skus']} SKU · Model {summary['model_version']}",
       f"Tổng SKU–ngày kỳ vọng có bán: {summary['expected_sale_sku_days']:.2f}",
       f"Nhãn có bán theo ngưỡng {summary['threshold']:.2f}: {summary['predicted_sale_sku_days']}",
       f"SKU cần rà soát: {summary['alert_count']}",'', 'Theo ngày:']
    for x in summary['daily']:
        lines.append(f"• {x['ForecastDate']}: {x['ExpectedSellingSKUs']:.2f} SKU kỳ vọng có bán")
    lines.extend(['','Phân nhóm ADI/CV²:'])
    for name in ['Smooth','Erratic','Intermittent','Lumpy','Insufficient Data']:
        lines.append(f"• {name}: {summary['behavior_counts'].get(name,0)} SKU")
    if summary['alerts']:
        lines.extend(['','SKU nên xem xét (chênh lệch lịch sử và dự báo):'])
        for a in summary['alerts'][:3]:
            lines.append(f"• {a['sku']} | {a['behavior_group']} | lịch sử {a['historical_sale_rate']:.0%}, dự báo {a['mean_forecast_sale_probability']:.0%}")
    if summary['warnings']:
        lines.extend(['','Lưu ý kiểm soát dữ liệu:'])
        lines.extend('• '+str(x)[:130] for x in summary['warnings'][:3])
    lines.extend(['','Chỉ là xác suất có phát sinh bán theo dữ liệu ghi nhận; không phải số lượng bán hay khuyến nghị nhập hàng.'])
    return '\n'.join(lines)[:3950]
