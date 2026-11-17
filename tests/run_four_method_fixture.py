"""Exercise the same four dispatch routes used by the application.

Requires the application's Python dependencies, licensed MATLAB/toolboxes and
Praat. This is an integration/normalization check, not a clinical validation.
"""
from pathlib import Path
import sys,importlib.util,argparse,json,csv,math
import numpy as np,pandas as pd
from generate_compatibility_fixtures import generate
ROOT=Path(__file__).resolve().parents[1]
def main(args):
 out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True);rows=generate(out/'fixtures')
 script=ROOT/'avhi_rff_method_comparison_gui_MATLAB_BRIDGE_v25_OPTIONAL_STI.py';spec=importlib.util.spec_from_file_location('rff_application_fixture',script);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
 cfg=mod.RFFConfig();cfg.matlab_path=args.matlab;cfg.praat_path=args.praat;cfg.ap_bridge_dir=str(ROOT/'aRFF_AP_ROI_bridge');cfg.mb_bridge_dir=str(ROOT/'rff_auto_mb_roi_bridge');cfg.matlab_timeout_s=1200;cfg.save_debug_plots=False
 results=[]
 for row in rows:
  for method in ['AVHI_PRAAT_STRICT','RFF_CEPSTRAL']:
   if method=='AVHI_PRAAT_STRICT':r=mod.compute_praat_based_rff(row['Filepath'],row['Subject'],'afa',1,row['FricStart'],row['FricEnd'],cfg,method,strict=True)
   else:r=mod.compute_cepstral_rff(row['Filepath'],row['Subject'],'afa',1,row['FricStart'],row['FricEnd'],cfg)
   record=dict(Subject=row['Subject'],Method=method,OffValid=bool(r.off_valid),OnValid=bool(r.on_valid))
   for side in ['off','on']:
    values=getattr(r,side+'_rff');valid=getattr(r,side+'_valid')
    if valid:
     assert len(values)==10 and np.isfinite(values).all();assert abs(values[0 if side=='off' else -1])<1e-10
   results.append(record)
 manifest=str(out/'fixtures/manifest.csv')
 for method,runner in [('RFF_MB_ROI_MATLAB',mod.run_mb_matlab_bridge),('RFF_AP_ROI_MATLAB',mod.run_ap_matlab_bridge)]:
  rc,stdout,stderr,command,files=runner(manifest,out,cfg);(out/(method+'.log')).write_text(stdout+'\n'+stderr,encoding='utf-8');assert rc==0,(method,rc,stderr)
  frame=pd.read_csv(files['wide']);assert len(frame)==2 and not frame.duplicated(['Subject','Token','Rep']).any()
  for r in frame.to_dict('records'):
   record=dict(Subject=r['Subject'],Method=method,OffValid=bool(r['OffValid']),OnValid=bool(r['OnValid']))
   for side,title in [('OFF','Off'),('ON','On')]:
    if record[title+'Valid']:
     values=np.array([r[side+str(k)] for k in range(1,11)]);assert np.isfinite(values).all();assert abs(values[0 if side=='OFF' else -1])<1e-10
   results.append(record)
 assert len(results)==8
 frame=pd.DataFrame(results);assert frame.groupby('Method').size().eq(2).all()
 assert frame[['OffValid','OnValid']].to_numpy().any(),'No accepted voiced side was exercised'
 counts=frame.groupby('Method')[['OffValid','OnValid']].sum().astype(int).reset_index().to_dict('records')
 report=dict(Status='PASS',Methods=4,Signals=2,Rows=8,ROIs='Same .48–.63 s /f/ boundaries for all methods',Dispatch='Actual application Python and MATLAB bridge entry points',Scope='Integration, normal returns, output shape, accepted-side reference-cycle normalization and native rejection behavior; no accuracy or native-localization claim. A method may reject both fixtures; its accepted-value normalization is then not exercised by this integration layer.',Accepted_side_counts=counts,Results=results)
 (out/'FOUR_METHOD_INTEGRATION.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--matlab',required=True);p.add_argument('--praat',required=True);p.add_argument('--out',required=True);main(p.parse_args())
