"""Reproduce the matched-transition and synthetic-error tests and summaries."""
import argparse
from pathlib import Path
import itertools
import collections
import numpy as np,pandas as pd
from scipy.stats import friedmanchisquare,wilcoxon
METHODS=['AVHI_PRAAT_STRICT','RFF_MB_ROI_MATLAB','RFF_AP_ROI_MATLAB','RFF_CEPSTRAL']
LABEL=dict(zip(METHODS,['TC-ROI','MB','aRFF-AP','cRFF']))

def holm(pvalues):
 p=np.asarray(pvalues,float);order=np.argsort(p);corrected=np.maximum.accumulate(p[order]*(len(p)-np.arange(len(p))));answer=np.empty(len(p));answer[order]=np.minimum(corrected,1);return answer
def signed_test(a,b):
 if np.all(np.asarray(a)==np.asarray(b)):return 1.
 return float(wilcoxon(a,b,zero_method='wilcox',method='auto').pvalue)
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("real_transition_csv",type=Path)
 parser.add_argument("synthetic_endpoint_csv",type=Path)
 parser.add_argument("stimulus_manifest",type=Path)
 parser.add_argument("output",type=Path)
 args=parser.parse_args()
 out=args.output;out.mkdir(parents=True,exist_ok=True)
 t=pd.read_csv(args.real_transition_csv);s=pd.read_csv(args.synthetic_endpoint_csv);pairs=[];omnibus=[]
 for outcome in ['OFF10','ON1']:
  w=t.pivot(index=['Subject','Token','Rep'],columns='MethodCode',values=outcome).reindex(columns=METHODS).dropna();z=w.groupby('Subject').mean()
  test=friedmanchisquare(*[z[k] for k in METHODS]);omnibus.append(dict(Dataset='real',Outcome=outcome,Scope='All-four common transitions, equal-weight participant means',Matched_transitions=len(w),Blocks=len(z),Statistic=test.statistic,P=test.pvalue))
  for a,b in itertools.combinations(METHODS,2):
   d=z[a]-z[b];pairs.append(dict(Dataset='real',Outcome=outcome,Scope='All-four common participant means',Method_A=a,Method_B=b,N=len(z),Mean_difference_ST=d.mean(),Median_difference_ST=d.median(),P=signed_test(z[a],z[b])))
 pd.DataFrame(pairs).assign(P_Holm_12=holm([r['P'] for r in pairs])).to_csv(out/'real_paired_location_tests.csv',index=False)
 available=[]
 for outcome in ['OffValid','OnValid','BothValid']:
  z=t.groupby(['Subject','MethodCode'])[outcome].mean().unstack('MethodCode').reindex(columns=METHODS)
  test=friedmanchisquare(*[z[k] for k in METHODS]);omnibus.append(dict(Dataset='real availability',Outcome=outcome,Scope='Each participant contributes nine submitted transitions per method',Matched_transitions=639,Blocks=len(z),Statistic=test.statistic,P=test.pvalue))
  for a,b in itertools.combinations(METHODS,2):available.append(dict(Outcome=outcome,Method_A=a,Method_B=b,Participants=len(z),Mean_fraction_difference_A_minus_B=float((z[a]-z[b]).mean()),P=signed_test(z[a],z[b])))
 pd.DataFrame(available).assign(P_Holm_18=holm([r['P'] for r in available])).to_csv(out/'real_paired_availability_tests.csv',index=False)
 synthetic_tests=[]
 metadata=pd.read_csv(args.stimulus_manifest).set_index('ID')
 sets=[('main_clean',s[(s.Suite=='main')&(s.Condition=='clean')]),('main_all',s[s.Suite=='main']),('harmonic_clean',s[s.Suite=='independent_source']),('compound',s[s.Suite=='compound'])]
 for scope,data in sets:
  for side,g in data.groupby('Side'):
   wide=g.pivot(index='ID',columns='Method',values='Error_ST').reindex(columns=METHODS).dropna().abs();z=wide.join(metadata[['Tract','F0','Vowel','Trajectory','Condition']]).groupby(['Tract','F0','Vowel','Trajectory','Condition'])[METHODS].mean()
   test=friedmanchisquare(*[z[k] for k in METHODS]);omnibus.append(dict(Dataset='synthetic accepted absolute error',Outcome=side,Scope=scope,Matched_transitions=len(wide),Blocks=len(z),Statistic=test.statistic,P=test.pvalue))
   for a,b in itertools.combinations(METHODS,2):synthetic_tests.append(dict(Scope=scope,Side=side,Method_A=a,Method_B=b,Matched_signals=len(wide),Configuration_blocks=len(z),Mean_absolute_error_A_ST=z[a].mean(),Mean_absolute_error_B_ST=z[b].mean(),P=signed_test(z[a],z[b])))
 pd.DataFrame(synthetic_tests).assign(P_Holm_48=holm([r['P'] for r in synthetic_tests])).to_csv(out/'synthetic_matched_error_tests.csv',index=False)
 pd.DataFrame(omnibus).assign(P_Holm_all_13=holm([r['P'] for r in omnibus])).to_csv(out/'omnibus_tests.csv',index=False)
 rejection=[];components=[]
 for method,g in t.groupby('MethodCode'):
  for side,field,valid in [('OFF','OffReject','OffValid'),('ON','OnReject','OnValid')]:
   rejected=g[g[valid]==0];counts=rejected[field].fillna('').value_counts()
   for reason,n in counts.items():rejection.append(dict(Method=method,Side=side,Reason=reason,N=n,Rejected_total=len(rejected),Submitted=len(g)))
   c=collections.Counter()
   for reason in rejected[field].fillna(''):
    for item in set(x.strip() for x in str(reason).split(';') if x.strip()):c[item]+=1
   for reason,n in c.items():components.append(dict(Method=method,Side=side,Reason_component=reason,N=n,Rejected_total=len(rejected),Note='Components can co-occur; counts must not be summed.'))
 pd.DataFrame(rejection).to_csv(out/'real_rejection_reasons.csv',index=False);pd.DataFrame(components).to_csv(out/'real_rejection_components.csv',index=False)
 selected=[]
 for scope,data in sets:
  for (method,side),g in data.groupby(['Method','Side']):
   accepted=g[g.Accepted==True];gap=-accepted.Selected_end_displacement_ms if side=='OFF' else accepted.Selected_start_displacement_ms
   selected.append(dict(Scope=scope,Method=method,Side=side,Submitted=len(g),Accepted=len(accepted),Availability_percent=len(accepted)/len(g)*100,Canonical_MAE_ST=accepted.Error_ST.abs().mean(),Canonical_P95_absolute_ST=accepted.Error_ST.abs().quantile(.95),Median_nearest_edge_gap_ms=gap.median(),Nearest_edge_gap_P05_ms=gap.quantile(.05),Nearest_edge_gap_P95_ms=gap.quantile(.95),Across_boundary_N=int((gap< -1e-6).sum()),Note='Edge gap is not physical GCI marking error; pulse/trough/phase origins differ.'))
 pd.DataFrame(selected).to_csv(out/'synthetic_endpoint_and_boundary_summary.csv',index=False)
 checks=[]
 for method,g in t.groupby('MethodCode'):
  checks.append(dict(Method=method,Submitted=len(g),OFF=int(g.OffValid.sum()),ON=int(g.OnValid.sum()),Both=int(g.BothValid.sum())))
 print(pd.DataFrame(omnibus).to_string(index=False))
if __name__=='__main__':main()
