function [acf,lags,bounds] = autocorr(x, maxlag)
%AUTOCORR Minimal normalized autocorrelation helper for aRFF-AP bridge.
% Returns acf for lags 0:maxlag. This is included so the bridge does not
% require the Econometrics Toolbox implementation of autocorr.
if nargin < 2 || isempty(maxlag)
    maxlag = min(20, numel(x)-1);
end
x = double(x(:));
x = x - mean(x, 'omitnan');
x(~isfinite(x)) = 0;
maxlag = max(0, round(maxlag));
acf = zeros(maxlag+1,1);
if isempty(x) || all(x==0)
    lags = (0:maxlag)';
    bounds = [];
    return;
end
n = numel(x);
denom = sum(x.^2) + eps;
for lag = 0:maxlag
    if lag >= n
        acf(lag+1) = 0;
    else
        acf(lag+1) = sum(x(1:n-lag).*x(1+lag:n)) / denom;
    end
end
lags = (0:maxlag)';
bounds = [];
end
