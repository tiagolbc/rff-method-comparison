function y = smooth(x, span)
%SMOOTH Minimal compatibility helper for aRFF-AP bridge.
% Uses moving median when smoothdata is available; otherwise moving average.
if nargin < 2 || isempty(span)
    span = 5;
end
span = max(1, round(span));
x = double(x(:));
try
    y = smoothdata(x, 'movmedian', span);
catch
    b = ones(span,1)./span;
    try
        y = filtfilt(b, 1, x);
    catch
        y = conv(x, b, 'same');
    end
end
end
