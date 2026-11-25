"""Refit exploratory vote, interaction, and rating-session analyses."""
import hashlib
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm
from model_helpers import analysis_directory, ci_icc, fit_model, icc

A=analysis_directory(__doc__)
M={'RFF-Praat-ROI':'RFF-TC-ROI','Cepstral-assisted RFF':'cRFF'}
t=pd.read_csv(A/'inputs/RFF_transition_level_v24.csv',low_memory=False);t.Method=t.Method.replace(M)
r=pd.read_csv(A/'ratings_all_originals_and_retests.csv');D=['Overall','Roughness','Breathiness','Strain','Instability']
sub=sorted(t.Subject.unique());p=r[r.Session.eq('Original')&r.Subject.isin(sub)]
refs={'all_seven':p.groupby('Subject')[D].mean().reset_index(),'Judge01':p[p.Judge.eq('Judge 01')][['Subject']+D],'Judge04':p[p.Judge.eq('Judge 04')][['Subject']+D],'six_without_J02':p[~p.Judge.eq('Judge 02')].groupby('Subject')[D].mean().reset_index()}
votes=[];inputs=[];interactions=[]
for method,folder,fn in [('RFF-TC-ROI','python_on050_fallback','rff_all_traces_wide.csv'),('RFF-TC-ROI','python_on050_no_fallback','rff_all_traces_wide.csv'),('RFF-MB','mb_on050_fallback','rff_mb_roi_results_wide.csv'),('RFF-MB','mb_on050_no_fallback','rff_mb_roi_results_wide.csv')]:
    arrays=[]
    for group in ("Normal Group", "Altered Group"):
        dst=A/"inputs/symmetric_vote"/group/folder/fn
        data=pd.read_csv(dst,low_memory=False)
        inputs.append({"Input":dst.relative_to(A).as_posix(),"SHA256":hashlib.sha256(dst.read_bytes()).hexdigest()})
        if method=='RFF-TC-ROI':data=data[data.Method.astype(str).str.startswith(('AVHI_PRAAT_STRICT','RFF_PRAAT_ROI_SENS'))]
        arrays.append(data)
    v=pd.concat(arrays,ignore_index=True)
    if 'Rep' not in v:v['Rep']=v.Instance
    v=v[['Subject','Token','Rep','ON1','OnValid']];assert not v.duplicated(['Subject','Token','Rep']).any()
    meta=t[t.Method.eq(method)][['Subject','Method','Token','Rep','Age','Sex','CPPSStatus']]
    dd=meta.merge(v,on=['Subject','Token','Rep'],validate='one_to_one');assert len(dd)==639
    dd.loc[~dd.OnValid.astype(bool),'ON1']=np.nan
    for name,x in refs.items():
        g=dd.merge(x,on='Subject',validate='many_to_one');out,_,_,_=fit_model(g,'ON1')
        votes.append({'Reference':name,'Method':method,'Condition':folder,'N_valid_ON':g.ON1.notna().sum(),'N_subjects':g.loc[g.ON1.notna(),'Subject'].nunique(),**out})
pd.DataFrame(votes).to_csv(A/'symmetric_vote_models_all_references.csv',index=False)
(A/'symmetric_vote_input_manifest.json').write_text(json.dumps(inputs,indent=2),encoding='utf8')
for name,x in refs.items():
    for method,gg in t.groupby('Method'):
        base=gg[['Subject','Method','Token','Rep','Age','Sex','CPPSStatus','OFF10','ON1']].merge(x,on='Subject',validate='many_to_one')
        _,_,X,ok=fit_model(base,'ON1')
        for kind,pairs in [('perceptual',[('Strain','Roughness'),('Strain','Breathiness')]),('token',[('Strain','ifi'),('Strain','ufu')])]:
            XX=X.copy()
            for c1,c2 in pairs:XX[c1+'x'+c2]=XX[c1]*XX[c2]
            fit=sm.OLS(base.loc[ok,'ON1'],XX.loc[ok]).fit().get_robustcov_results(cov_type='cluster',groups=base.loc[ok,'Subject'],use_correction=True,use_t=False)
            C=np.zeros((2,len(XX.columns)));C[0,-2]=C[1,-1]=1
            interactions.append({'Reference':name,'Method':method,'Interaction':kind,'Joint_p':float(fit.wald_test(C,scalar=True).pvalue),'Term1_p':float(fit.pvalues[-2]),'Term2_p':float(fit.pvalues[-1])})
pd.DataFrame(interactions).to_csv(A/'interaction_models_all_primary_references.csv',index=False)
# Later-session repeatability is distinct from the within-export Copia pairing.
later=pd.read_csv(A/"inputs/judge02_alternate_ratings.csv")
later=later[later.Session.eq("Original")][["Subject"]+D]
orig=r[r.Judge.eq('Judge 02')&r.Session.eq('Original')]
cross=orig.merge(later,on='Subject',suffixes=('_original','_later'),validate='one_to_one');out=[]
for scope,g in [('74_recordings',cross),('71_analytical',cross[cross.Subject.isin(sub)])]:
    for dim in D:
        z=g[[dim+'_original',dim+'_later']].to_numpy();ci=ci_icc(z)
        out.append({'Scope':scope,'Dimension':dim,'N':len(z),'ICC_A1':icc(z)[0],'CI_low':ci[0],'CI_high':ci[1],'Mean_later_minus_original':np.mean(z[:,1]-z[:,0])})
pd.DataFrame(out).to_csv(A/'Tiago_between_session_repeatability.csv',index=False)

print('R07 sensitivity models recalculated from current acoustic inputs')
