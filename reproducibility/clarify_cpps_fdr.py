from model_helpers import analysis_directory
import pandas as pd
from statsmodels.stats.multitest import multipletests
p=analysis_directory("Calculate CPPS multiplicity within each endpoint")/'CPPS_stratum_models_reproduced.csv'
d=pd.read_csv(p)
d['FDR_4_per_outcome']=d.groupby('Outcome')['p'].transform(lambda x:multipletests(x,method='fdr_bh')[1])
d.to_csv(p,index=False)
print('CPPS four-method families added; existing eight-test correction retained.')
