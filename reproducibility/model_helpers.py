"""Reliability and clustered regression functions used in the study analyses."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

def analysis_directory(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("directory", type=Path, help="Working directory with the required local inputs")
    return parser.parse_args().directory.resolve()

def icc(a):
    a=np.asarray(a,float);n,k=a.shape
    gm=a.mean(); rm=a.mean(axis=1);cm=a.mean(axis=0)
    msr=k*np.sum((rm-gm)**2)/(n-1);msc=n*np.sum((cm-gm)**2)/(k-1)
    mse=np.sum((a-rm[:,None]-cm[None,:]+gm)**2)/((n-1)*(k-1))
    den=msr+(k-1)*mse+k*(msc-mse)/n
    single=(msr-mse)/den if den else np.nan
    avg=(msr-mse)/(msr+(msc-mse)/n) if msr+(msc-mse)/n else np.nan
    return single,avg
def ci_icc(a,seed=20261023,B=2000):
    a=np.asarray(a,float);rng=np.random.default_rng(seed)
    vals=np.array([icc(a[rng.integers(0,len(a),len(a))]) for _ in range(B)])
    return np.nanpercentile(vals,[2.5,97.5],axis=0).T.reshape(-1)


def fit_model(d,y,weight=None):
    cov=pd.DataFrame({'const':1.,'Strain':d.Strain/10,'Roughness':d.Roughness/10,'Breathiness':d.Breathiness/10,'Age':(d.Age-30)/10,'Male':d.Sex.eq('Male').astype(float),'CPPSAltered':d.CPPSStatus.eq('Altered').astype(float),'ifi':d.Token.eq('ifi').astype(float),'ufu':d.Token.eq('ufu').astype(float)},index=d.index)
    ok=d[y].notna()&cov.notna().all(axis=1)
    dd=d.loc[ok];X=cov.loc[ok]
    if weight is None: base=sm.OLS(dd[y],X).fit()
    else:base=sm.WLS(dd[y],X,weights=np.asarray(weight)[ok]).fit()
    res=base.get_robustcov_results(cov_type='cluster',groups=dd.Subject,use_correction=True,df_correction=True,use_t=False)
    ci=res.conf_int();return {'N_rows':len(dd),'N_subjects':dd.Subject.nunique(),'Beta':res.params[1],'SE':res.bse[1],'CI_low':ci[1,0],'CI_high':ci[1,1],'p':res.pvalues[1]},res,cov,ok
