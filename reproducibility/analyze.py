"""Reproduce the frozen acoustic results and audit the expanded rating panel.
All outputs are derived from read-only source files. No participant values are edited.
"""
import hashlib
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from model_helpers import analysis_directory, ci_icc, fit_model, icc

OUT=analysis_directory(__doc__)
IN=OUT/"inputs"
M={'RFF-Praat-ROI':'RFF-TC-ROI','RFF-MB':'RFF-MB','aRFF-AP':'aRFF-AP','Cepstral-assisted RFF':'cRFF'}
DIMS=['Overall','Roughness','Breathiness','Strain','Instability']
files=[]
def source(name):
    file=IN/name
    files.append({"source": f"inputs/{name}", "sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "bytes": file.stat().st_size})
    return file

t=pd.read_csv(source("RFF_transition_level_v24.csv")); t.Method=t.Method.replace(M)
source("RFF_cycle_level_v24.csv")
subjects=sorted(t.Subject.unique()); assert len(subjects)==71
assert len(t)==639*4 and not t.duplicated(['Subject','Token','Rep','Method']).any()
assert (t.groupby(['Subject','Method']).size()==9).all()
assert (t.BothValid==(t.OffValid*t.OnValid)).all()
for col,v in [('OFF10','OffValid'),('ON1','OnValid')]: assert (t[col].notna()==t[v].eq(1)).all()
avail=t.groupby('Method',sort=False).agg(N=('Subject','size'),OFF=('OffValid','sum'),ON=('OnValid','sum'),Both=('BothValid','sum')).reset_index()
for k in ['OFF','ON','Both']:avail[k+'_pct']=avail[k]/avail.N*100
avail.to_csv(OUT/'availability.csv',index=False)
wide=t.pivot(index=['Subject','Token','Rep'],columns='Method',values='BothValid')
exclusive=wide.index[(wide.cRFF==1)&(wide.drop(columns='cRFF').sum(axis=1)==0)]
pd.DataFrame(exclusive.tolist(),columns=['Subject','Token','Rep']).to_csv(OUT/'cRFF_exclusive_22.csv',index=False)
# Exclusive count is recomputed after fresh extraction.

r=pd.read_csv(source("ratings_all_originals_and_retests.csv"))
dups=r[r.duplicated(["Subject","Judge","Session"],keep=False)]
assert len(dups)==2 and dups.Subject.nunique()==1
assert dups.Judge.eq("Judge 02").all() and dups.Session.eq("Retest").all()
dups.to_csv(OUT/"ambiguous_repeat_records.csv",index=False)
r.to_csv(OUT/"ratings_all_originals_and_retests.csv",index=False)
primary=r[r.Session.eq('Original')&r.Subject.isin(subjects)].copy()
assert (primary.groupby('Judge').size()==71).all()
assert all(set(g.Subject)==set(subjects) for _,g in primary.groupby('Judge'))
n_excluded=len(set(r.Subject)-set(subjects))
intra=[]; pairs=[]
for judge,g in r.groupby('Judge'):
    p=g[g.Session.eq('Original')].merge(g[g.Session.eq('Retest')].drop_duplicates('Subject',keep=False),on=['Subject','Judge'],suffixes=('_Original','_Retest'),validate='one_to_one')
    pairs.append(p)
    for dim in DIMS:
        a=p[[dim+'_Original',dim+'_Retest']].to_numpy()
        val=icc(a)[0]; lo,hi=ci_icc(a)[:2]
        intra.append({'Judge':judge,'Dimension':dim,'N_pairs_all_74':len(a),'ICC_A1':val,'CI_low_bootstrap':lo,'CI_high_bootstrap':hi,'Mean_retest_minus_original':np.mean(a[:,1]-a[:,0]),'MAE':np.mean(abs(a[:,1]-a[:,0])),'Pairs_in_71':p.Subject.isin(subjects).sum()})
pd.concat(pairs).to_csv(OUT/'ret-test_pairs_audit.csv',index=False)
intr=pd.DataFrame(intra); intr.to_csv(OUT/'intrarater_ICC.csv',index=False)
inter=[]
panels={'five_without_J01_J02':[f'Judge {i:02d}' for i in [3,4,5,6,7]],'six_without_J02':[f'Judge {i:02d}' for i in [1,3,4,5,6,7]],'six_without_J07':[f'Judge {i:02d}' for i in range(1,7)],'five_without_J03_J07':[f'Judge {i:02d}' for i in [1,2,4,5,6]],'all_seven':[f'Judge {i:02d}' for i in range(1,8)],'six_without_J03':[f'Judge {i:02d}' for i in range(1,8) if i!=3],'all_five':['Judge 01','Judge 02','Judge 03','Judge 04','Judge 05'],'four_without_J03':['Judge 01','Judge 02','Judge 04','Judge 05'],'three_current':['Judge 01','Judge 02','Judge 03']}
for panel,judges in panels.items():
    for dim in DIMS:
        a=primary.pivot(index='Subject',columns='Judge',values=dim)[judges].to_numpy()
        a1,ak=icc(a);c1l,c1u,ckl,cku=ci_icc(a)
        inter.append({'Panel':panel,'Dimension':dim,'N':len(a),'K':len(judges),'ICC_A1':a1,'ICC_Ak':ak,'A1_CI_low':c1l,'A1_CI_high':c1u,'Ak_CI_low':ckl,'Ak_CI_high':cku})
inter=pd.DataFrame(inter);inter.to_csv(OUT/'interrater_ICC.csv',index=False)
distribution=[]
for judge,g in primary.groupby('Judge'):
    for dim in DIMS:
        v=g[dim]
        distribution.append({'Judge':judge,'Dimension':dim,'N':len(v),'Mean':v.mean(),'SD':v.std(),'Median':v.median(),'Q1':v.quantile(.25),'Q3':v.quantile(.75),'Min':v.min(),'Max':v.max(),'N_gt23_3':(v>23.3).sum()})
pd.DataFrame(distribution).to_csv(OUT/'rating_distributions.csv',index=False)
# Preserve the submitted Judge 01 reference; all other revision references use current files.
refs={}
x=t.drop_duplicates('Subject')[['Subject']+['Leo'+d for d in ['Overall','Roughness','Breathiness','Tension','Instability']]].copy()
x.columns=['Subject']+DIMS;refs['submission_J01']=x
for judge in sorted(primary.Judge.unique()): refs['current_'+judge.replace(' ','')]=primary[primary.Judge.eq(judge)][['Subject']+DIMS].copy()
for panel,judges in panels.items():refs[panel]=primary[primary.Judge.isin(judges)].groupby('Subject')[DIMS].mean().reset_index()
later=pd.read_csv(source("judge02_alternate_ratings.csv"))
refs['later_Tiago_session']=later[later.Session.eq('Original')&later.Subject.isin(subjects)][['Subject']+DIMS].copy()
refs['seven_with_later_Tiago']=(primary[~primary.Judge.eq('Judge 02')].groupby('Subject')[DIMS].sum()+refs['later_Tiago_session'].set_index('Subject')[DIMS]).div(7).reset_index()
models=[];vmodels=[];weighted=[];groups=[];allparams=[]
basecols=['Subject','Method','Token','Rep','Age','Sex','CPPSStatus','OffValid','OnValid','BothValid','OFF10','ON1']
common=t.pivot(index=['Subject','Token','Rep'],columns='Method',values='OnValid').min(axis=1)
keys=set(common[common.eq(1)].index)
for ref,x in refs.items():
    d=t[basecols].merge(x,on='Subject',validate='many_to_one')
    for method,g in d.groupby('Method',sort=False):
        for outcome in ['OFF10','ON1']:
            out,res,cov,ok=fit_model(g,outcome);models.append({'Reference':ref,'Method':method,'Outcome':outcome,**out})
            if ref=='submission_J01':
                for ii,term in enumerate(cov.columns):
                    allparams.append({'Method':method,'Outcome':outcome,'Term':term,'Beta':res.params[ii],'SE':res.bse[ii],'p':res.pvalues[ii],'CI_low':res.conf_int()[ii,0],'CI_high':res.conf_int()[ii,1]})
            # Selection model conditions on measured covariates; does not identify MNAR mechanisms.
            indicator=g.OnValid if outcome=='ON1' else g.OffValid
            fit=sm.GLM(indicator,cov,family=sm.families.Binomial()).fit(cov_type='cluster',cov_kwds={'groups':g.Subject,'use_correction':True})
            for term in ['Strain','Roughness','Breathiness']:
                ci=fit.conf_int().loc[term]
                vmodels.append({'Reference':ref,'Method':method,'Outcome':outcome,'Term':term,'OR':np.exp(fit.params[term]),'CI_low':np.exp(ci[0]),'CI_high':np.exp(ci[1]),'p':fit.pvalues[term]})
            if outcome=='ON1':
                prob=np.asarray(fit.predict(cov)); out,_,_,_=fit_model(g,outcome,1/prob)
                weighted.append({'Reference':ref,'Method':method,'Analysis':'IPW_untruncated',**out,'Min_predicted_probability':prob.min(),'Max_weight_valid':(1/prob[np.asarray(indicator,dtype=bool)]).max()})
                out,_,_,_=fit_model(g,outcome,1/np.clip(prob,.05,.95))
                weighted.append({'Reference':ref,'Method':method,'Analysis':'IPW_prob_clipped_05_95',**out,'Min_predicted_probability':prob.min(),'Max_weight_valid':(1/np.clip(prob,.05,.95)[np.asarray(indicator,dtype=bool)]).max()})
                idx=[(s,tok,rep) in keys for s,tok,rep in zip(g.Subject,g.Token,g.Rep)]
                out,_,_,_=fit_model(g.loc[idx],outcome);weighted.append({'Reference':ref,'Method':method,'Analysis':'common_ON1',**out})
        # Four descriptive groups based on historical 23.3 threshold; not diagnostic.
        s=g.groupby('Subject').agg(OFF10=('OFF10','mean'),ON1=('ON1','mean'),Roughness=('Roughness','first'),Breathiness=('Breathiness','first'),Strain=('Strain','first'))
        rb=(s.Roughness>23.3)|(s.Breathiness>23.3); st=s.Strain>23.3
        s['Group']=np.select([~rb&~st,rb&~st,~rb&st,rb&st],['Typical','RB_without_strain','Isolated_strain','RB_plus_strain'],default='Unclassified')
        for outcome in ['OFF10','ON1']:
            arr=[a[outcome].dropna().values for _,a in s.groupby('Group')]
            kw=stats.kruskal(*arr) if len(arr)>1 else None
            groups.append({'Reference':ref,'Method':method,'Outcome':outcome,'N_groups':len(arr),'H':kw.statistic if kw else np.nan,'p':kw.pvalue if kw else np.nan,**{f'n_{name}':int(n) for name,n in s.Group.value_counts().items()}})
disp=pd.DataFrame([{'Reference':name,'N':len(x),'Strain_mean':x.Strain.mean(),'Strain_SD':x.Strain.std(ddof=1),'Strain_min':x.Strain.min(),'Strain_max':x.Strain.max()} for name,x in refs.items()]);disp.to_csv(OUT/'reference_strain_dispersion.csv',index=False)
models=pd.DataFrame(models).merge(disp[['Reference','Strain_SD']],on='Reference',validate='many_to_one')
for term in ['Beta','SE','CI_low','CI_high']:models[term+'_per_SD']=models[term]*models.Strain_SD/10
models['FDR_8']=models.groupby('Reference').p.transform(lambda p:multipletests(p,method='fdr_bh')[1]);models.to_csv(OUT/'adjusted_strain_models_all_references.csv',index=False)
pd.DataFrame(vmodels).to_csv(OUT/'validity_models_all_references.csv',index=False)
pd.DataFrame(weighted).to_csv(OUT/'IPW_and_common_support_all_references.csv',index=False)
pd.DataFrame(groups).to_csv(OUT/'four_group_comparisons_all_references.csv',index=False)
pd.DataFrame(allparams).to_csv(OUT/'submission_models_all_coefficients.csv',index=False)
summary={
    "N_judges":7,"N_participants":len(subjects),"N_transitions":639,
    "N_exclusive_cRFF":len(exclusive),"N_common_ON1":len(keys),
    "N_common_subjects":len({x[0] for x in keys}),"N_excluded_perceptual":n_excluded,
    "Python":sys.version,"numpy":np.__version__,"pandas":pd.__version__,
    "statsmodels":sm.__version__,"ICC_bootstraps":2000,"seed":20261023,
}
(OUT/'analysis_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
(OUT/'input_manifest.json').write_text(json.dumps(files,indent=2),encoding='utf8')
print(avail.to_string(index=False))
print(intr[intr.Dimension.eq('Strain')].to_string(index=False))
print(inter[inter.Dimension.eq('Strain')].to_string(index=False))
print(models[models.Reference.isin(['submission_J01','current_Judge04'])].to_string(index=False))
print('Done')
