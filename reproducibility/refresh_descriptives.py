"""Participant-level agreement, descriptive subsets and common-transition tests."""
import itertools
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
from model_helpers import analysis_directory, icc

OUT=analysis_directory(__doc__)
t=pd.read_csv(OUT/'inputs/RFF_transition_level_v24.csv')
M={'RFF-Praat-ROI':'RFF-TC-ROI','RFF-MB':'RFF-MB','aRFF-AP':'aRFF-AP','Cepstral-assisted RFF':'cRFF'}
t.Method=t.Method.replace(M);methods=list(M.values());KEY=['Subject','Token','Rep']
agreement=[]
for outcome in ['OFF10','ON1']:
    a=t.groupby(['Subject','Method'])[outcome].mean().unstack()
    for i,m1 in enumerate(M.values()):
        for m2 in list(M.values())[i+1:]:
            dat=a[[m1,m2]].dropna();x,y=dat.to_numpy().T
            ccc=2*np.cov(x,y,ddof=1)[0,1]/(np.var(x,ddof=1)+np.var(y,ddof=1)+(x.mean()-y.mean())**2)
            rng=np.random.default_rng(20261023);boots=[]
            for b in range(5000):
                bx,by=dat.to_numpy()[rng.integers(0,len(dat),len(dat))].T
                bc=2*np.cov(bx,by,ddof=1)[0,1]/(np.var(bx,ddof=1)+np.var(by,ddof=1)+(bx.mean()-by.mean())**2)
                boots.append([bc,icc(np.c_[bx,by])[0],np.mean(abs(by-bx))])
            lo,hi=np.percentile(boots,[2.5,97.5],axis=0);diff=y-x
            agreement.append({'Outcome':outcome,'Method1':m1,'Method2':m2,'N':len(x),'CCC_sample_moments':ccc,'CCC_CI_low':lo[0],'CCC_CI_high':hi[0],'ICC_A1':icc(np.c_[x,y])[0],'ICC_CI_low':lo[1],'ICC_CI_high':hi[1],'Spearman':stats.spearmanr(x,y).statistic,'Pearson':stats.pearsonr(x,y).statistic,'Bias_M2_minus_M1':diff.mean(),'MAE':np.mean(abs(diff)),'MAE_CI_low':lo[2],'MAE_CI_high':hi[2],'RMSE':np.sqrt(np.mean(diff**2)),'LoA_low':diff.mean()-1.96*diff.std(ddof=1),'LoA_high':diff.mean()+1.96*diff.std(ddof=1)})
pd.DataFrame(agreement).to_csv(OUT/'method_agreement.csv',index=False)

wide=t.pivot(index=KEY,columns='Method',values='BothValid').reindex(columns=methods)
subsets={'All four complete':wide.min(axis=1).eq(1),'None complete':wide.max(axis=1).eq(0),'TC complete / AP incomplete':wide['RFF-TC-ROI'].eq(1)&wide['aRFF-AP'].eq(0),'TC complete / cRFF incomplete':wide['RFF-TC-ROI'].eq(1)&wide['cRFF'].eq(0),'cRFF only complete':wide.cRFF.eq(1)&wide.drop(columns='cRFF').sum(axis=1).eq(0)}
ac=pd.read_csv(OUT/'transition_acoustic_properties.csv');differential=[]
for name,mask in subsets.items():
 keys=wide.index[mask];z=ac.set_index(KEY).loc[keys].reset_index();row={'Subset':name,'N_transitions':len(keys),'N_speakers':len(set(keys.get_level_values('Subject')))}
 for side,g in z.groupby('Side'):
  # Column names match the independent acoustic audit retained with R06.
  for col in ['CPPS_dB','NAC_median']:
   if col in g:
    q=g[col].quantile([.25,.5,.75]);row.update({f'{side}_{col}_q25':q.loc[.25],f'{side}_{col}_median':q.loc[.5],f'{side}_{col}_q75':q.loc[.75]})
 differential.append(row)
pd.DataFrame(differential).to_csv(OUT/'differential_acceptance_R07.csv',index=False)
groups=[]
for (group,method),g in t.groupby(['PerceptualGroup4','Method'],sort=False):
 s=g.groupby('Subject')[['OFF10','ON1']].mean();groups.append(dict(Group=group,Method=method,OFF_mean=s.OFF10.mean(),OFF_SD=s.OFF10.std(),ON_mean=s.ON1.mean(),ON_SD=s.ON1.std(),Both_pct=g.BothValid.mean()*100,N_participants=len(s)))
pd.DataFrame(groups).to_csv(OUT/'group_RFF_descriptives.csv',index=False)
omni=[];pairs=[]
for outcome in ['OFF10','ON1']:
 w=t.pivot(index=KEY,columns='Method',values=outcome).reindex(columns=methods).dropna();z=w.groupby('Subject').mean();f=stats.friedmanchisquare(*[z[x] for x in methods]);omni.append(dict(Outcome=outcome,N_transitions=len(w),N_participants=len(z),Friedman_chi2=f.statistic,p=f.pvalue))
 for a,b in itertools.combinations(methods,2):
  d=z[a]-z[b];r=stats.wilcoxon(d) if d.ne(0).any() else type('R',(),{'statistic':0,'pvalue':1})();pairs.append(dict(Outcome=outcome,Method_A=a,Method_B=b,N=len(z),Mean_difference_ST=d.mean(),Wilcoxon_W=r.statistic,p=r.pvalue))
pp=pd.DataFrame(pairs);pp['Holm_12']=multipletests(pp.p,method='holm')[1];pp.to_csv(OUT/'same_ROI_paired_location_tests.csv',index=False)
oo=pd.DataFrame(omni);oo['Holm_2']=multipletests(oo.p,method='holm')[1];oo.to_csv(OUT/'same_ROI_omnibus_tests.csv',index=False)
reasons=[]
for side in ['Off','On']:
 for (m,reason),n in t[t[side+'Valid'].eq(0)].groupby(['Method',side+'Reject'],dropna=False).size().items():reasons.append(dict(Method=m,Side=side,Reason=reason,N=n))
pd.DataFrame(reasons).to_csv(OUT/'rejection_reason_counts_R07.csv',index=False)
