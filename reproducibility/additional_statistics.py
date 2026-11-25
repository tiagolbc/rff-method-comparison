"""Calculate the descriptive groups, CPPS, self-report, and vocal-history analyses."""
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests
from model_helpers import analysis_directory

OUT=analysis_directory(__doc__)
t=pd.read_csv(OUT/'inputs/RFF_transition_level_v24.csv');sub=t.drop_duplicates('Subject')
rows=[]
for grp,g in sub.groupby('PerceptualGroup4'):
    rows.append({'Group':grp,'N':len(g),'Age_mean':g.Age.mean(),'Age_SD':g.Age.std(),'Female':g.Sex.eq('Female').sum(),'Male':g.Sex.eq('Male').sum(),'CPPS_typical':g.CPPSStatus.eq('Normal').sum(),'CPPS_altered':g.CPPSStatus.eq('Altered').sum(),**{d+'_mean':g[d].mean() for d in ['Overall','Roughness','Breathiness','Tension','Instability']},**{d+'_SD':g[d].std() for d in ['Overall','Roughness','Breathiness','Tension','Instability']}})
pd.DataFrame(rows).to_csv(OUT/'submission_group_characteristics_full.csv',index=False)
def design(g):return pd.DataFrame({'const':1.,'strain':g.Tension/10,'roughness':g.Roughness/10,'breathiness':g.Breathiness/10,'age':(g.Age-30)/10,'male':g.Sex.eq('Male').astype(float),'CPPS':g.CPPSStatus.eq('Altered').astype(float),'ifi':g.Token.eq('ifi').astype(float),'ufu':g.Token.eq('ufu').astype(float)},index=g.index)
def fit(g,y,X):
    ok=g[y].notna()&X.notna().all(axis=1)
    return sm.OLS(g.loc[ok,y],X.loc[ok]).fit().get_robustcov_results(cov_type='cluster',groups=g.loc[ok,'Subject'],use_correction=True,use_t=False)
inter=[];cpps=[];selfs=[];history=[];binary=[]
for m,g in t.groupby('Method'):
    X=design(g);XX=X.copy();XX['strain_x_roughness']=XX.strain*XX.roughness;XX['strain_x_breathiness']=XX.strain*XX.breathiness
    rr=fit(g,'ON1',XX);test=np.zeros((2,XX.shape[1]));test[0,-2]=test[1,-1]=1
    inter.append({'Method':m,'Test':'strain_by_roughness_and_breathiness','Joint_chisq_p':float(rr.wald_test(test,scalar=True).pvalue),'roughness_interaction_p':rr.pvalues[-2],'breathiness_interaction_p':rr.pvalues[-1]})
    XX=X.copy();XX['strain_x_ifi']=XX.strain*XX.ifi;XX['strain_x_ufu']=XX.strain*XX.ufu;rr=fit(g,'ON1',XX)
    inter.append({'Method':m,'Test':'strain_by_token','Joint_chisq_p':float(rr.wald_test(test,scalar=True).pvalue)})
    for y in ['OFF10','ON1']:
        xx=X[['const','age','male','CPPS','ifi','ufu']];rr=fit(g,y,xx);ci=rr.conf_int()[3]
        cpps.append({'Method':m,'Outcome':y,'Beta':rr.params[3],'CI_low':ci[0],'CI_high':ci[1],'p':rr.pvalues[3]})
    ss=g.groupby('Subject').agg(MeanOFF10=('OFF10','mean'),MeanON1=('ON1','mean'),Availability=('BothValid','mean'),AnyTension=('AnyTension','first'),Borg=('Borg','first'),ESVTotal=('ESVTotal','first'),ESVLimitation=('ESVLimitation','first'),ESVEmotional=('ESVEmotional','first'),ESVPhysical=('ESVPhysical','first'))
    for o in ['MeanOFF10','MeanON1','Availability']:
        for v in ['Borg','ESVTotal','ESVLimitation','ESVEmotional','ESVPhysical']:
            x=ss[[o,v]].dropna();rho,p=stats.spearmanr(x[o],x[v]);selfs.append({'Method':m,'Outcome':o,'Measure':v,'N':len(x),'rho':rho,'p':p})
    for y in ['MeanOFF10','MeanON1']:
        a=ss.loc[ss.AnyTension.eq(0),y].dropna().values;b=ss.loc[ss.AnyTension.eq(1),y].dropna().values
        dif=b[:,None]-a[None,:]
        binary.append({'Method':m,'Outcome':y,'Mean_without':np.mean(a),'Mean_with':np.mean(b),'Cliff_delta':np.mean(dif>0)-np.mean(dif<0),'p':stats.mannwhitneyu(a,b,alternative='two-sided').pvalue})
    for var in ['ProfessionalVoiceUser','HadVoiceProblem','PreviousVoiceTherapy','RefluxSymptoms','AllergyRespiratoryHistory']:
        for y in ['OFF10','ON1']:
            xx=X.copy();xx[var]=pd.to_numeric(g[var],errors='coerce');rr=fit(g,y,xx)
            history.append({'Method':m,'Outcome':y,'Variable':var,'Beta':rr.params[-1],'p':rr.pvalues[-1]})
pd.DataFrame(inter).to_csv(OUT/'submission_interaction_tests_reproduced.csv',index=False)
for fn,rows in [('CPPS_stratum_models_reproduced',cpps),('selfreport_correlations_reproduced',selfs),('history_models_reproduced',history)]:
    d=pd.DataFrame(rows);d['FDR_all_tests_in_file']=multipletests(d.p,method='fdr_bh')[1];d.to_csv(OUT/(fn+'.csv'),index=False)
pd.DataFrame(binary).to_csv(OUT/'binary_strain_comparisons_reproduced.csv',index=False)
# Refit the original sensitivity outputs without rerunning MATLAB or changing source outputs.
votes=[];vote_comp=[]
for method,folder,file in [('RFF-TC-ROI','python_on050_fallback','rff_all_traces_wide.csv'),('RFF-TC-ROI','python_on050_no_fallback','rff_all_traces_wide.csv'),('RFF-MB','mb_on050_fallback','rff_mb_roi_results_wide.csv'),('RFF-MB','mb_on050_no_fallback','rff_mb_roi_results_wide.csv')]:
    arrays=[]
    for group in ("Normal Group", "Altered Group"):
        data=pd.read_csv(OUT/"inputs/symmetric_vote"/group/folder/file,low_memory=False)
        if method=='RFF-TC-ROI':data=data[data.Method.astype(str).str.startswith(('AVHI_PRAAT_STRICT','RFF_PRAAT_ROI_SENS'))]
        # MATLAB bridge uses output Instance or Rep and bridge subject labels; resolve via accompanying manifest if needed.
        arrays.append(data)
    v=pd.concat(arrays,ignore_index=True)
    if 'Rep' not in v:v['Rep']=v['Instance']
    # The exported external MATLAB Subject uses the analytical subject; confirm unique joins.
    relevant=v[['Subject','Token','Rep','ON1','OnValid']].copy()
    if relevant.duplicated(['Subject','Token','Rep']).any():raise ValueError('Duplicate vote input')
    meta=t[t.Method.eq('RFF-Praat-ROI' if method=='RFF-TC-ROI' else 'RFF-MB')].drop(columns=['ON1','OnValid'])
    dd=meta.merge(relevant,on=['Subject','Token','Rep'],how='left',validate='one_to_one')
    assert len(dd)==639 and dd.OnValid.notna().all()
    dd.loc[~dd.OnValid.astype(bool),'ON1']=np.nan
    rr=fit(dd,'ON1',design(dd));ci=rr.conf_int()[1]
    votes.append({'Method':method,'Condition':folder,'N_valid_ON':dd.ON1.notna().sum(),'N_subjects':dd.loc[dd.ON1.notna(),'Subject'].nunique(),'Beta':rr.params[1],'CI_low':ci[0],'CI_high':ci[1],'p':rr.pvalues[1]})
    orig=meta.merge(t[t.Method.eq('RFF-Praat-ROI' if method=='RFF-TC-ROI' else 'RFF-MB')][['Subject','Token','Rep','ON1']],on=['Subject','Token','Rep'])
    comp=orig[['Subject','Token','Rep','ON1']].merge(dd[['Subject','Token','Rep','ON1']],on=['Subject','Token','Rep'],suffixes=('_original','_sensitivity')).dropna()
    delta=comp.ON1_sensitivity-comp.ON1_original
    vote_comp.append({'Method':method,'Condition':folder,'N_common':len(delta),'N_identical_1e_6':int((abs(delta)<=1e-6).sum()),'Mean_absolute_difference_ST':np.mean(abs(delta))})
pd.DataFrame(votes).to_csv(OUT/'symmetric_vote_models_reproduced.csv',index=False)
pd.DataFrame(vote_comp).to_csv(OUT/'symmetric_vote_output_comparison.csv',index=False)
print('Additional statistical reproduction complete')
