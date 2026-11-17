function y = smooth(x,span)
%SMOOTH Moving-average compatibility for the finite vector calls in aRFF-AP.
% Implements the documented default smooth(x,span) operation. This is not
% the full Curve Fitting Toolbox API (lowess, abscissae and NaNs unsupported).
x=double(x(:));n=numel(x);if nargin<2 || isempty(span),span=5;end
assert(isscalar(span) && isfinite(span) && span>0,'RFF:SmoothSpan','Span must be a positive finite scalar');
if isempty(x),y=x;return;end
assert(all(isfinite(x)),'RFF:SmoothFinite','This compatibility helper requires finite vector input');
if span<1,span=ceil(span*n);end
span=min(n,max(1,round(span)));if mod(span,2)==0,span=span-1;end
half=(span-1)/2;k=(1:n)';radius=min([repmat(half,n,1),k-1,n-k],[],2);
left=k-radius;right=k+radius;c=[0;cumsum(x)];y=(c(right+1)-c(left))./(right-left+1);
end
