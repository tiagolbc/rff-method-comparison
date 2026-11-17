function report=compare_mb_original(repoRoot,manifestPath,praatExe,outDir,originalMB)
% Execute the supplied original MB script from an isolated writable copy.
% Coincident anchors isolate compatibility; real separate ROI edges are a
% deliberately different input protocol. Never edit original source files.
maxNumCompThreads(1);set(groot,'defaultFigureVisible','off');
assert(~contains(outDir,' '),'Use a scratch path without spaces for the original Praat transport');
oldPath=path;oldDir=pwd;cleanup=onCleanup(@()restore(oldPath,oldDir)); %#ok<NASGU>
restoredefaultpath;
stage=fullfile(outDir,'original');mkdir(stage);copyfile(fullfile(originalMB,'*'),stage);
audio=fullfile(outDir,'audio');mkdir(audio);
m=readtable(manifestPath,'VariableNamingRule','preserve','TextType','string');
for i=1:height(m),copyfile(char(m.Filepath(i)),fullfile(audio,char(m.Filename(i))));end
% The original command transport does not quote paths; supply a portable
% executable copy in the same space-free scratch directory without editing it.
portablePraat=fullfile(outDir,'Praat.exe');copyfile(praatExe,portablePraat);
% Windows GUI executables need synchronous batch transport to capture stdout.
% This wrapper changes only process transport/encoding, never pulse arguments.
wrapper=fullfile(outDir,'praat_stdout.cmd');stdout=fullfile(outDir,'praat_stdout.txt');
f=fopen(wrapper,'w');fprintf(f,'@echo off\r\n"%s" --utf8 %%* > "%s"\r\ntype "%s"\r\n',portablePraat,stdout,stdout);fclose(f);
global praatPath;praatPath=wrapper;
% Invoke one recording at a time. The supplied script clears its nbytes loop
% bookkeeping variable after its first file; no original source is altered.
original=table();
for k=1:height(m)
 one=fullfile(outDir,sprintf('native_audio_%d',k));mkdir(one);copyfile(char(m.Filepath(k)),fullfile(one,char(m.Filename(k))));
 audDir=[one filesep];files=dir(fullfile(one,'*.wav'));file_count=1;starti=1;
 fricLocs=table(m.Filename(k),(m.FricStart(k)+m.FricEnd(k))/2,'VariableNames',{'Filename','FricLoc'});
 OFF_Reject=cell(1,1);ON_Reject=cell(1,1);Filename=cell(1,1);OFF_pulse=zeros(1,11);ON_pulse=zeros(1,11);
 save(fullfile(stage,'Dependencies','tempWS.mat'),'audDir','files','file_count','starti','fricLocs','OFF_Reject','ON_Reject','Filename','OFF_pulse','ON_pulse');
 cd(stage);addpath(fullfile(stage,'Dependencies'));part=execute_original(fullfile(stage,'RFF_auto_MB.m'));original=[original;part];cd(oldDir); %#ok<AGROW>
end
% Bridge now receives the same single center as the original.
addpath(fullfile(repoRoot,'rff_auto_mb_roi_bridge'));
m.Filepath=string(fullfile(audio,m.Filename));m.FricLoc=(m.FricStart+m.FricEnd)/2;m=removevars(m,{'FricStart','FricEnd'});
manifest=fullfile(outDir,'matched_manifest.csv');writetable(m,manifest);
RFF_auto_MB_ROI_bridge(manifest,fullfile(outDir,'adapted'),praatExe,'SaveXlsx',false);
adapted=readtable(fullfile(outDir,'adapted','rff_mb_roi_results_wide.csv'),'VariableNamingRule','preserve','TextType','string');
report=struct('Compared_rows',height(m),'Max_landmark_difference_seconds',0,'Max_RFF_difference_ST',0,'Scope','Original script and ROI bridge on identical full-file audio with coincident FricLoc anchors; does not assert equivalence after changing separate ROI edges/crops.');
for i=1:height(original)
 name=string(original.Filename(i));j=find(adapted.Filename==name);assert(numel(j)==1);
 for s=1:2
  if s==1,prefix='OFF';title='Off';else,prefix='ON';title='On';end
  cols=startsWith(original.Properties.VariableNames,[prefix '_pulse_']);pulses=table2array(original(i,cols));
  valid=all(pulses>0);assert(valid==logical(adapted.([title 'Valid'])(j)),['Acceptance mismatch: ' char(name) ' ' prefix]);
  if valid
   actual=zeros(1,11);for k=1:11,actual(k)=adapted.(sprintf('%s_pulse_%02d_s',prefix,k))(j);end
   lm=max(abs(actual-pulses));report.Max_landmark_difference_seconds=max(report.Max_landmark_difference_seconds,lm);
   hz=1./diff(pulses);if s==1,ref=hz(1);else,ref=hz(end);end
   target=12*log2(hz/ref);values=zeros(1,10);for k=1:10,values(k)=adapted.(sprintf('%s%d',prefix,k))(j);end
   delta=max(abs(values-target));report.Max_RFF_difference_ST=max(report.Max_RFF_difference_ST,delta);
   assert(lm<1e-8 && delta<1e-6,'Matched native/ROI numerical mismatch');
  end
 end
end
f=fopen(fullfile(outDir,'MB_MATCHED_ORIGINAL_COMPATIBILITY.json'),'w');fprintf(f,'%s',jsonencode(report));fclose(f);disp(report);
end
function rffout=execute_original(scriptPath)
run(scriptPath);
end
function restore(p,d)
path(p);cd(d);
end
