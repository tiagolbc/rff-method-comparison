function y = prctile(x, p, varargin)
% Minimal local fallback for prctile() used by the MB ROI bridge.
% Supports vector inputs and scalar/vector percentiles.
x = x(:);
x = x(isfinite(x));
p = double(p);
if isempty(x)
    y = NaN(size(p));
    return;
end
x = sort(double(x));
n = numel(x);
y = NaN(size(p));
for k = 1:numel(p)
    pk = min(max(p(k), 0), 100);
    if n == 1
        y(k) = x(1);
    else
        pos = 1 + (pk/100) * (n - 1);
        lo = floor(pos); hi = ceil(pos);
        if lo == hi
            y(k) = x(lo);
        else
            y(k) = x(lo) + (pos - lo) * (x(hi) - x(lo));
        end
    end
end
end
