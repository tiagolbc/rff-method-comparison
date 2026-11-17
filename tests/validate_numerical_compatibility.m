function validate_numerical_compatibility(root)
maxNumCompThreads(1);oldPath=path;cleanup=onCleanup(@()path(oldPath));restoredefaultpath;rng(20261116);report=struct; %#ok<NASGU>
ap=fullfile(root,'aRFF_AP_ROI_bridge','dependencies');
mb=fullfile(root,'rff_auto_mb_roi_bridge','Dependencies');
% Obtain base-MATLAB percentiles before adding the restricted bridge helper.
X={1:10,randn(1,11),randn(1,20),[0 0 1 8 9],42};P=[0 5 25 50 65 75 95 100];native=cell(size(X));
for i=1:numel(X),native{i}=prctile(X{i},P);end
report.Native_percentile_path=which('prctile');addpath(mb);clear prctile;err=0;
for i=1:numel(X),err=max(err,max(abs(prctile(X{i},P)-native{i})));end
assert(err<1e-12);report.Percentile_max_absolute_error=err;rmpath(mb);clear prctile;
addpath(ap);err=0;cases=0;
for n=[1 2 3 5 10 101 1000]
 x=randn(n,1);
 for span=[1 2 3 4 5 17 101 .1 .51]
  if span<1,w=ceil(span*n);else,w=round(span);end
  w=min(n,max(1,w));if mod(w,2)==0,w=w-1;end
  target=zeros(n,1);
  for k=1:n,r=min([(w-1)/2,k-1,n-k]);target(k)=mean(x(k-r:k+r));end
  err=max(err,max(abs(smooth(x,span)-target)));cases=cases+1;
 end
end
assert(err<1e-11);assert(isequal(smooth([0 0 10 0 0],5),[0;10/3;2;10/3;0]));
report.Smooth_reference='Independent direct means, documented finite uniformly indexed vector domain';report.Smooth_cases=cases;report.Smooth_max_absolute_error=err;
% The AP waveform-shape call uses two finite nonconstant equal-length vectors,
% scaling enabled, no reflection: check its residual against signed least squares.
% This checks the implemented finite-vector formula, not native binary parity.
err=0;
for i=1:100
 x=randn(100,1);y=randn(100,1);xc=x-mean(x);yc=y-mean(y);
 b=(yc'*xc)/(yc'*yc);target=sum((xc-b*yc).^2)/sum(xc.^2);
 err=max(err,abs(procrustes(x,y,'reflection',false)-target));
end
assert(err<1e-12);report.Procrustes_1D_max_absolute_error=err;
err=0;
for i=1:100
 x=randn(200,1);z=x-mean(x);v=xcorr(z,20,'biased');target=v(21:end)/v(21);
 err=max(err,max(abs(autocorr(x,20)-target)));
end
assert(err<1e-12);report.Autocorr_finite_vector_max_absolute_error=err;
report.Limitations='Smooth is checked against documented finite-vector semantics, not an installed Curve Fitting Toolbox binary. Autocorr and procrustes checks cover mathematical finite-vector AP call forms, not the full toolbox APIs or degenerate inputs.';
report.MATLAB=version;f=fopen(fullfile(tempdir,'RFF_NUMERICAL_COMPATIBILITY_VALIDATION.json'),'w');fprintf(f,'%s',jsonencode(report));fclose(f);disp(report);
end
