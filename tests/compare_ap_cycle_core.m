function report=compare_ap_cycle_core(repoRoot,manifestPath,outDir,originalAP)
% Compare ORIGINAL and ROI cycle functions under MATCHED anchors/conditioning.
% This intentionally isolates the cycle core, not the GUI/localization workflow.
% originalAP must be the extracted supplied original AP directory.
maxNumCompThreads(1);set(groot,'defaultFigureVisible','off');
oldPath=path;cleanupPath=onCleanup(@()path(oldPath)); %#ok<NASGU>
ap=fullfile(repoRoot,'aRFF_AP_ROI_bridge');addpath(ap);addpath(fullfile(ap,'dependencies'));addpath(fullfile(ap,'dependencies','swipe'));
manifest=readtable(manifestPath,'TextType','string','VariableNamingRule','preserve');
% Run the actual production adapter first: full pitch, preparation and output.
run_arff_ap_roi_bridge(manifestPath,outDir,ap);
global perform_fol;perform_fol=[fullfile(outDir,'aRFF_internal') filesep];
files=dir(fullfile(perform_fol,'*'));report=struct('Compared_sides',0,'Max_RFF_difference_ST',0,'Max_landmark_difference_samples',0,'Scope','Original cycle routine versus ROI routine with identical prepared inputs and coincident anchors; not full native localization equivalence');
for i=1:numel(files)
 if ~files(i).isdir || startsWith(files(i).name,'.'),continue;end
 filename=[files(i).name '.wav'];fol=fullfile(perform_fol,files(i).name,'var');fric=fullfile(fol,'fric_param.mat');
 if ~isfile(fric),continue;end
 S=load(fric);S.fric_start_loc=S.pk_loc;S.fric_end_loc=S.pk_loc;save(fric,'-struct','S');
 audio=[fullfile(outDir,'_arff_ap_roi_work_audio') filesep];
 % Use the supplied original routine, retaining compatibility dependencies.
 addpath(fullfile(originalAP,'dependencies'),'-begin');clear find_RFFcycles_aswipep;
 expected=strrep(fullfile(originalAP,'dependencies','find_RFFcycles_aswipep.m'),'\','/');
 actual=strrep(which('find_RFFcycles_aswipep'),'\','/');
 assert(strcmpi(expected,actual),'Original routine not resolved');
 find_RFFcycles_aswipep(audio,filename,false);
 originals=cell(S.totalinst,2);
 for j=1:S.totalinst
  for side=1:2
   label=side_label(side);p=fullfile(fol,[num2str(j) '_' label '.mat']);originals{j,side}=load(p);
  end
 end
 find_RFFcycles_aswipep_roi_native(audio,filename,false);
 for j=1:S.totalinst
  for side=1:2
   label=side_label(side);v=load(fullfile(fol,[num2str(j) '_' label '.mat']));a=originals{j,side}.aRFF;b=v.aRFF;
   assert(isequaln(a,b),'Original/ROI full cycle-state mismatch under matched inputs');
   for field={'peak_array','trough_array','peak_RFF','trough_RFF','sigtype','rej_code'}
    name=field{1};assert(isfield(a,name)==isfield(b,name),name);
    if isfield(a,name)
     assert(isequal(size(a.(name)),size(b.(name))),name);
     assert(isequaln(a.(name),b.(name)),['Native/ROI cycle mismatch: ' name]);
    end
   end
   report.Compared_sides=report.Compared_sides+1;
  end
 end
end
assert(report.Compared_sides==2*height(manifest),'Missing fixture comparisons');
f=fopen(fullfile(outDir,'AP_MATCHED_CORE_COMPATIBILITY.json'),'w');fprintf(f,'%s',jsonencode(report));fclose(f);
end
function label=side_label(i)
if i==1,label='off';else,label='on';end
end
