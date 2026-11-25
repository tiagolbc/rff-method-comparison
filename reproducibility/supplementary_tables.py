from pathlib import Path
from model_helpers import fit_model
import argparse
from itertools import combinations
import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

parser=argparse.ArgumentParser(description="Build aggregate supplementary comparison tables.")
parser.add_argument("analysis_directory",type=Path)
parser.add_argument("output",type=Path)
args=parser.parse_args()
A=args.analysis_directory; O=args.output; O.mkdir(exist_ok=True,parents=True)
def load(n):return pd.read_csv(A/n,low_memory=False)
def save(d,n):pd.DataFrame(d).to_csv(O/(n+'.csv'),index=False)
M=['RFF-TC-ROI','RFF-MB','aRFF-AP','cRFF']
aliases={'AVHI_PRAAT_STRICT':M[0],'RFF_PRAAT_ROI':M[0],'RFF-Praat-ROI':M[0],'RFF_MB_ROI_MATLAB':M[1],'RFF_AP_ROI_MATLAB':M[2],'RFF_CEPSTRAL':M[3],'Cepstral-assisted RFF':M[3]}
key=['Subject','Token','Rep']
t=load('inputs/RFF_transition_level_v24.csv')
t.Method=t.Method.replace(aliases)
assert set(t.Method)==set(M) and len(t)==2556 and t.Subject.nunique()==71 and not t.duplicated(key+['Method']).any()
assert t.groupby('Method').BothValid.sum().loc[M].tolist()==[534,510,242,207]
for y,v in [('OFF10','OffValid'),('ON1','OnValid')]:
 assert np.array_equal(t[y].notna(),t[v].eq(1))
def stats(w,a,b,scale,side,ntrans=None,boot=False):
 x,y=w[[a,b]].to_numpy().T
 delta=y-x
 vx,vy=np.var(x,ddof=1),np.var(y,ddof=1)
 ccc=2*np.cov(x,y,ddof=1)[0,1]/(vx+vy+(y.mean()-x.mean())**2)
 sd=np.std(delta,ddof=1)
 rec=dict(Support=scale,Endpoint=side,Method_A=a,Method_B=b,N_observations=len(w),
   N_participants=w.index.get_level_values('Subject').nunique(),N_transitions=ntrans,
   CCC=ccc,Bias_B_minus_A=delta.mean(),Median_B_minus_A=np.median(delta),
   Mean_absolute_difference=np.abs(delta).mean(),LoA_low=delta.mean()-1.96*sd,LoA_high=delta.mean()+1.96*sd,
   Empirical_low=np.quantile(delta,.025),Empirical_high=np.quantile(delta,.975),
   Absolute_difference_below_0_01_ST=int((np.abs(delta)<.01).sum()),
   Absolute_difference_above_1_ST=int((np.abs(delta)>1).sum()))
 return rec
rows=[]
for y,cnt,nperson in [('OFF10',226,68),('ON1',164,59)]:
 w=t.pivot(index=key,columns='Method',values=y)[M]
 native=w.groupby('Subject').mean()
 common=w.dropna()
 assert (len(common),common.index.get_level_values('Subject').nunique())==(cnt,nperson)
 equal=common.groupby('Subject').mean()
 for a,b in combinations(M,2):
  rows.append(stats(native[[a,b]].dropna(),a,b,'available participant means',y))
  rows.append(stats(equal,a,b,'all-four shared participant means',y,cnt))
  rows.append(stats(common,a,b,'all-four shared transitions',y,cnt))
  pair=w[[a,b]].dropna()
  rows.append(stats(pair,a,b,'pairwise shared transitions',y,len(pair)))
save(rows,'agreement_all_pairs')
out=pd.DataFrame(rows)
old=load('method_agreement.csv')
for r in old.itertuples():
 z=out[(out.Support=='available participant means')&(out.Endpoint==r.Outcome)&(out.Method_A==r.Method1)&(out.Method_B==r.Method2)]
 if len(z):
  assert abs(z.CCC.iloc[0]-r.CCC_sample_moments)<1e-10,(r,z)
  assert abs(z.Bias_B_minus_A.iloc[0]-r.Bias_M2_minus_M1)<1e-10
print(out[(out.Method_A==M[0])&(out.Method_B==M[1])][['Support','Endpoint','N_observations','CCC','Bias_B_minus_A','Median_B_minus_A','LoA_low','LoA_high']].round(3).to_string(index=False))

r=load('ratings_all_originals_and_retests.csv')
dims=['Overall','Roughness','Breathiness','Strain','Instability']
p=r[r.Session.eq('Original')&r.Subject.isin(t.Subject)]
assert len(p)==71*7 and not p.duplicated(['Subject','Judge']).any()
panel=p.groupby('Subject')[dims].mean()
judge=p[p.Judge.eq('Judge 01')].set_index('Subject')[dims]
sc=t.drop_duplicates('Subject').set_index('Subject')
for c,k in [('LeoRoughness','Roughness'),('LeoBreathiness','Breathiness'),('LeoTension','Strain')]:
 assert np.allclose(sc.loc[judge.index,c],judge[k])
w=t.pivot(index=key,columns='Method',values='BothValid')[M].astype(bool)
masks={'All four complete':w.all(axis=1),'None complete':~w.any(axis=1),
 'TC complete / AP incomplete':w[M[0]]&~w[M[2]],
 'TC complete / cRFF incomplete':w[M[0]]&~w[M[3]],
 'cRFF only complete':w[M[3]]&~w[M[:3]].any(axis=1)}
rows=[]
for label,mask in masks.items():
 subjects=w.loc[mask].index.get_level_values('Subject').unique()
 v=panel.loc[subjects]
 rec=dict(Subset=label,Transitions=mask.sum(),Participants=len(subjects))
 for c in ['Roughness','Breathiness','Strain']:
  rec[c+'_mean']=v[c].mean();rec[c+'_SD']=v[c].std()
 rows.append(rec)
assert [(x['Transitions'],x['Participants']) for x in rows]==[(62,39),(35,25),(317,71),(363,70),(22,19)]
save(rows,'acceptance_subset_perception')
rows=[]
for (method,sex),g in t.groupby(['Method','Sex']):
 rows.append(dict(Method=method,Sex=sex,N=len(g),Participants=g.Subject.nunique(),OFF=int(g.OffValid.sum()),ON=int(g.OnValid.sum()),Complete=int(g.BothValid.sum())))
save(rows,'availability_by_sex')
ipw=load('IPW_and_common_support_all_references.csv')
rec=[]
for ref, ratings in {'all_seven':panel,'submission_J01':judge}.items():
 for m,g in t.groupby('Method'):
  d=g[['Subject','Token','Rep','Age','Sex','CPPSStatus','OnValid','ON1']].merge(ratings,on='Subject',validate='many_to_one')
  _,_,X,_=fit_model(d,'ON1')
  fit=sm.GLM(d.OnValid,X,family=sm.families.Binomial()).fit()
  use=d.OnValid.eq(1).to_numpy()
  prob=np.asarray(fit.predict(X))
  w=1/prob[use]
  actual,_,_,_=fit_model(d,'ON1',1/prob)
  prev=ipw[(ipw.Reference==ref)&(ipw.Method==m)&(ipw.Analysis=='IPW_untruncated')].iloc[0]
  assert np.allclose([prev.Beta, prev.Max_weight_valid],[actual['Beta'], w.max()],atol=1e-8),(ref,m)
  rec.append(dict(Reference=ref,Method=m,N=len(w),Min=w.min(),Max=w.max(),ESS=w.sum()**2/(w@w)))
save(rec,'IPW_diagnostics')
models=load('adjusted_strain_models_all_references.csv')
assert models.groupby('Reference').size().eq(8).all()
on=models[(models.Outcome=='ON1')&models.Reference.isin([f'current_Judge{i:02d}' for i in range(3,8)])]
print('Strain analysis references',len(models.Reference.unique()),'tests',len(models))
print(on[['Reference','Method','Beta','p','FDR_8']].round(4).to_string(index=False))
refs={'seven-judge mean':panel,**{j:g.set_index('Subject')[dims] for j,g in p.groupby('Judge')}}
rows=[]
for name,v in refs.items():
 corr=v[['Roughness','Breathiness','Strain']].corr()
 rows.append(dict(Reference=name,N=len(v),Strain_Roughness=corr.loc['Strain','Roughness'],Strain_Breathiness=corr.loc['Strain','Breathiness'],Roughness_Breathiness=corr.loc['Roughness','Breathiness']))
save(rows,'perceptual_correlations')
omni=load('additional_comparisons/omnibus_tests.csv')
avail=omni[omni.Dataset.eq('real availability')].copy()
for i,z in avail.iterrows():
 vals=t.groupby(['Subject','Method'])[z.Outcome].mean().unstack()[M]
 test=friedmanchisquare(*(vals[m] for m in M))
 assert np.allclose([test.statistic,test.pvalue],[z.Statistic,z.P],rtol=1e-8,atol=1e-40)
avail['Holm_within_3']=multipletests(avail.P,method='holm')[1]
save(avail,'availability_omnibus')
for n,tab in {
 'validity_seven_J01':load('validity_models_all_references.csv').query("Reference in ['all_seven','submission_J01']"),
 'IPW_and_common_ON1':ipw.query("Analysis in ['IPW_untruncated','common_ON1']"),
 'vote_J04':load('symmetric_vote_models_all_references.csv').query("Reference=='Judge04'"),
 'STI_J01':load('STI_reproduction/tables/STI_primary_strain_models_min2.csv'),
 'STI_exact_common':load('STI_reproduction/tables/STI_exact_common_support_strain_models.csv'),
}.items():
 assert len(tab),n
 save(tab,n)
l=load('reprocessed_real/fresh_landmarks.csv')
assert len(l)==3801*11
(l.groupby('Method').size()//11).to_csv(O/'accepted_landmark_counts.csv')
print('Outputs verified')
