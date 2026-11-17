function y = prctile(x,p,varargin)
%PRCTILE Vector compatibility with MATLAB default midpoint percentiles.
% Restricted to the vector/scalar-percentile call used by the MB bridge.
% The interpolation locations are (i-0.5)/n (Hyndman-Fan type 5).
assert(isvector(x) || isempty(x),'RFF:PercentileVector','Vector input required');
assert(isempty(varargin),'RFF:PercentileOptions','Optional API not implemented');
x=double(x(:));x=x(isfinite(x));p=double(p);y=NaN(size(p));
assert(all(isfinite(p(:))) && all(p(:)>=0 & p(:)<=100),'RFF:PercentileRange','Percentiles must lie in [0,100]');
if isempty(x),return;end
x=sort(x);n=numel(x);
for k=1:numel(p)
 pos=n*p(k)/100+0.5;
 if pos<=1,y(k)=x(1);elseif pos>=n,y(k)=x(n);
 else,lo=floor(pos);y(k)=x(lo)+(pos-lo)*(x(lo+1)-x(lo));end
end
end
