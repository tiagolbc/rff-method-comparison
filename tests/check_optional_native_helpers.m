function report=check_optional_native_helpers(repoRoot,outFile)
% Explicitly distinguish installed native-toolbox comparisons from skips.
oldPath=path;cleanup=onCleanup(@()path(oldPath));restoredefaultpath;rng(20261116); %#ok<NASGU>
x=randn(101,1);y=randn(101,1);names={'smooth','autocorr','procrustes'};native=cell(1,3);report=struct;
for i=1:3
 resolved=which(names{i});report.(names{i})=struct('Native_path',resolved,'Status','SKIPPED_NATIVE_TOOLBOX_UNAVAILABLE');
 if isempty(resolved),continue;end
 switch names{i}
  case 'smooth',native{i}=smooth(x,17);
  case 'autocorr',native{i}=autocorr(x,'NumLags',20);
  case 'procrustes',native{i}=procrustes(x,y,'reflection',false);
 end
end
addpath(fullfile(repoRoot,'aRFF_AP_ROI_bridge','dependencies'));
for i=1:3
 if isempty(native{i}),continue;end
 switch names{i}
  case 'smooth',actual=smooth(x,17);
  case 'autocorr',actual=autocorr(x,20);
  case 'procrustes',actual=procrustes(x,y,'reflection',false);
 end
 err=max(abs(actual(:)-native{i}(:)));assert(err<1e-10,[names{i} ' native mismatch']);report.(names{i}).Status='PASS_FINITE_CALL_FORM';report.(names{i}).Maximum_absolute_difference=err;
end
report.Scope='Native binary comparisons only when installed. Skips are not passes. No full toolbox API or interactive localization equivalence is claimed.';
f=fopen(outFile,'w');fprintf(f,'%s',jsonencode(report));fclose(f);disp(report);
end
