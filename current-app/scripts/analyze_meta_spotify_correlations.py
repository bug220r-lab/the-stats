"""Read-only, predeclared 14-comparison extension using repaired Meta Follows."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/reconciliation/meta_20261023/package'
OUT = ROOT / 'data/reconciliation/meta_spotify_crossref_20261023/correlations'
SEED = 20261023


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = ['spotify/cleaned/artist_daily.csv','social/account_daily.csv',
               'social/meta_collection/follows_daily_resolved.csv',
               'raw/spotify_baseline/normalized/release_metadata.csv',
               'cross_platform/statistical_results.csv','code/cross_platform.py']
    hashes = {p:hashlib.sha256((BASE/p).read_bytes()).hexdigest() for p in sources}
    spec=importlib.util.spec_from_file_location('prior_cross_platform',BASE/'code/cross_platform.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    sp=pd.read_csv(BASE/sources[0]); social=pd.read_csv(BASE/sources[1],dtype=str)
    follows=pd.read_csv(BASE/sources[2],dtype=str)
    for d in [sp,social,follows]: d['date']=pd.to_datetime(d['date'])
    for d in [social,follows]: d['value']=pd.to_numeric(d['value'],errors='coerce')
    assert not follows.date.duplicated().any() and len(follows)==293 and follows.value.notna().all()
    assert follows.value.sum()==326
    assert follows.partial_day.str.lower().eq('false').all()
    repaired=social[~((social.platform_selected=='Instagram')&(social.metric=='follows'))].copy()
    repaired=pd.concat([repaired,follows],ignore_index=True)
    assert not repaired.duplicated(['platform_selected','metric','date']).any()
    releases=pd.read_csv(BASE/sources[3]); releases['release_date']=pd.to_datetime(releases.release_date)
    rd=releases.loc[releases.release_date.dt.year==2026,'release_date']
    rw=set(mod.week_start(rd)); excluded=rw|{w+pd.Timedelta(weeks=1) for w in rw}
    yw=mod.weekly(sp,'daily_streams','Spotify UTC streams')
    predictors=mod.PREDICTORS+[('Instagram','follows')]
    results=[]; pairs_all=[]; weeks_all=[]; audit=[]
    for platform,metric in predictors:
        d=repaired[(repaired.platform_selected==platform)&(repaired.metric==metric)].copy()
        xw=mod.weekly(d,'value',platform+' '+metric+' Pacific')
        xw['platform']=platform;xw['metric']=metric;weeks_all.append(xw)
        for lag in (0,1):
            aid=f'{platform.lower()}_{metric}_lag{lag}'
            pairs=mod.make_pairs(xw,yw,lag);pairs['analysis_id']=aid;pairs_all.append(pairs)
            g=pairs.dropna(subset=['social_log_change','spotify_log_change']).copy()
            levels=pairs.dropna(subset=['social_value','spotify_streams'])
            x=g.social_log_change.to_numpy();y=g.spotify_log_change.to_numpy();n=len(g)
            rho=mod.rho(x,y)
            reason = ('Only three Facebook clicks in two weeks' if (platform,metric)==('Facebook','link_clicks') else
                      'Instagram clicks constant zero' if (platform,metric)==('Instagram','link_clicks') else
                      'Facebook interaction June regime break' if (platform,metric)==('Facebook','interactions') else '')
            eligible=bool(np.isfinite(rho) and not reason)
            event_mask=g.apply(lambda r:any(t in excluded for t in (r.social_week,r.spotify_week,r.social_week-pd.Timedelta(weeks=1),r.spotify_week-pd.Timedelta(weeks=1))),axis=1)
            no_event=g.loc[~event_mask]
            keep=np.ones(n,dtype=bool);keep[np.argsort(np.abs(y))[-2:]]=False
            loo=[mod.rho(np.delete(x,i),np.delete(y,i)) for i in range(n)]
            shifts={}
            for shift in (-1,1):
                shifted=mod.make_pairs(mod.weekly(d,'value',aid,shift),yw,lag).dropna(subset=['social_log_change','spotify_log_change'])
                shifts[shift]=mod.rho(shifted.social_log_change,shifted.spotify_log_change)
            record={'analysis_id':aid,'platform':platform,'metric':metric,'lag_weeks':lag,
                    'complete_weeks':int(xw.complete_week.sum()),'n_levels':len(levels),'n_changes':n,
                    'rho_change':rho,'rho_levels':mod.rho(levels.social_value,levels.spotify_streams),
                    'inference_eligible':eligible,'exclusion_reason':reason,
                    'p_circular':mod.circular_p(x,y) if eligible else np.nan,
                    'rho_no_release':mod.rho(no_event.social_log_change,no_event.spotify_log_change),
                    'n_no_release':len(no_event),'rho_no_top2':mod.rho(x[keep],y[keep]),
                    'loo_min':min(loo),'loo_max':max(loo),'rho_shift_minus1':shifts[-1],'rho_shift_plus1':shifts[1],
                    'social_change_acf1':pd.Series(x).autocorr(1) if len(np.unique(x))>1 else np.nan,
                    'lineage':'new repaired Follows extension' if metric=='follows' else 'original predictor recomputed unchanged'}
            for block in (2,4,6):
                ci=mod.bootstrap_ci(x,y,block=block,reps=2000,seed=SEED) if eligible else (np.nan,np.nan)
                record[f'ci95_low_block{block}'],record[f'ci95_high_block{block}']=ci
            results.append(record)
            audit.append({'analysis_id':aid,'daily_rows':len(d),'null_days_common':int(d.loc[d.date.between(mod.START,mod.END),'value'].isna().sum()),'duplicate_dates':int(d.date.duplicated().sum()),'complete_weeks':int(xw.complete_week.sum()),'n_pairs':n})
    result=pd.DataFrame(results)
    result['q_bh_14']=mod.bh(result.p_circular)
    result['q_by_14']=np.minimum(1,result.q_bh_14*sum(1/j for j in range(1,15)))
    result['p_holm_14']=mod.holm(result.p_circular)
    assert len(result)==14
    old=pd.read_csv(BASE/'cross_platform/statistical_results.csv')
    check=old.merge(result,on='analysis_id',suffixes=('_old','_new'),validate='one_to_one')
    assert len(check)==12
    assert np.allclose(check.rho_change_old,check.rho_change_new,equal_nan=True,atol=1e-12)
    assert np.allclose(check.p_circular_shift,check.p_circular,equal_nan=True,atol=1e-12)
    result.to_csv(OUT/'results.csv',index=False)
    pd.concat(pairs_all).to_csv(OUT/'weekly_pairs.csv',index=False)
    pd.concat(weeks_all).to_csv(OUT/'social_weeks.csv',index=False)
    yw.to_csv(OUT/'spotify_weeks.csv',index=False)
    pd.DataFrame(audit).to_csv(OUT/'join_audit.csv',index=False)
    summary={'executed_at_utc':datetime.now(timezone.utc).isoformat(),'input_version':'meta-collection-20261023',
             'planned_tests':14,'inference_eligible':int(result.inference_eligible.sum()),'q_bh_min':float(result.q_bh_14.min()),
             'q_under_05':int((result.q_bh_14<.05).sum()),'old_12_coefficients_and_p_match':True,
             'resolved_follows_days':len(follows),'resolved_follows_sum':float(follows.value.sum()),
             'release_dates':rd.dt.strftime('%Y-%m-%d').tolist(),'inputs_sha256':hashes,
             'method':'First differences log1p weekly counts, Spearman; 2000 circular block bootstrap; all circular shifts; fourteen-test BH/BY/Holm',
             'limitations':['Exploratory and assumption-dependent; no causal or conversion inference','Nominal UTC versus Pacific calendar weeks','Confidence intervals unadjusted, not simultaneous; rotation p-values coarse','FB interaction break and sparse/constant clicks excluded from inference']}
    assert hashes=={p:hashlib.sha256((BASE/p).read_bytes()).hexdigest() for p in sources}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(result[['analysis_id','n_changes','rho_change','rho_levels','p_circular','q_bh_14','rho_no_release','rho_no_top2','rho_shift_minus1','rho_shift_plus1']].to_string(index=False))
    print(json.dumps({k:v for k,v in summary.items() if k!='inputs_sha256'},indent=2))
    return result


if __name__=='__main__': run()
