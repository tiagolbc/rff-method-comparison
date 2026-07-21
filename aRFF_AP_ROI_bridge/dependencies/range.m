function y = range(x, dim)
% RANGE Local fallback for aRFF-AP ROI bridge.
%
% Some MATLAB installations do not expose range() unless Statistics and
% Machine Learning Toolbox or another toolbox is installed. The aRFF-AP code
% only requires numeric peak-to-peak range. This local fallback keeps the
% bridge self-contained by computing max(x)-min(x), omitting NaN values when
% possible.

if nargin < 2 || isempty(dim)
    x = x(:);
    x = x(isfinite(x));
    if isempty(x)
        y = NaN;
    else
        y = max(x) - min(x);
    end
else
    try
        y = max(x, [], dim, 'omitnan') - min(x, [], dim, 'omitnan');
    catch
        y = max(x, [], dim) - min(x, [], dim);
    end
end
end
