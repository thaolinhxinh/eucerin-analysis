"""Extract descriptive SKU behavior as of the same cutoff as inference."""
from .chapter6_pipeline import dim_behavior


def segment(panel, asof):
    frame=dim_behavior(panel,asof)
    frame['BehaviorDetail']=frame.BehaviorGroup
    frame.loc[frame.BehaviorGroup.isin(['No Sales','Insufficient Positive Observations']),'BehaviorGroup']='Insufficient Data'
    return frame
