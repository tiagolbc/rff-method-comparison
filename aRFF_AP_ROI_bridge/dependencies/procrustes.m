function [d, Z, transform] = procrustes(X, Y, varargin)
% Minimal local fallback for MATLAB procrustes() when Statistics Toolbox is
% unavailable. The aRFF-AP code uses only the first output as a waveform-shape
% mismatch score. This implementation supports the common call pattern:
%     d = procrustes(X, Y, 'reflection', false)
% and returns a Procrustes-like normalized residual.

reflection = true;
scaling = true;
for i = 1:2:numel(varargin)
    key = lower(char(varargin{i}));
    if i+1 <= numel(varargin)
        val = varargin{i+1};
        switch key
            case 'reflection'
                if ischar(val) || isstring(val)
                    reflection = ~strcmpi(char(val), 'false');
                else
                    reflection = logical(val);
                end
            case 'scaling'
                if ischar(val) || isstring(val)
                    scaling = ~strcmpi(char(val), 'false');
                else
                    scaling = logical(val);
                end
        end
    end
end

X = double(X);
Y = double(Y);
if isvector(X); X = X(:); end
if isvector(Y); Y = Y(:); end
n = min(size(X,1), size(Y,1));
p = min(size(X,2), size(Y,2));
X = X(1:n, 1:p);
Y = Y(1:n, 1:p);
valid = all(isfinite(X),2) & all(isfinite(Y),2);
X = X(valid,:);
Y = Y(valid,:);
if size(X,1) < 2 || isempty(X) || isempty(Y)
    d = Inf;
    Z = Y;
    transform = struct('T', eye(max(1,p)), 'b', 1, 'c', zeros(1,max(1,p)));
    return;
end

muX = mean(X,1);
muY = mean(Y,1);
X0 = X - muX;
Y0 = Y - muY;
ssX = sum(X0(:).^2);
ssY = sum(Y0(:).^2);
if ssX <= eps || ssY <= eps
    d = Inf;
    Z = Y;
    transform = struct('T', eye(p), 'b', 1, 'c', muX - muY);
    return;
end
normX = sqrt(ssX);
normY = sqrt(ssY);
Xn = X0 ./ normX;
Yn = Y0 ./ normY;

A = Yn' * Xn;
[U,S,V] = svd(A, 'econ');
T = U * V';
if ~reflection && det(T) < 0
    V(:,end) = -V(:,end);
    S(end,end) = -S(end,end);
    T = U * V';
end
traceTA = sum(diag(S));
if scaling
    b = traceTA * normX / normY;
else
    b = 1;
end
Z = normY .* Yn * T;
if scaling
    Z = b .* (Y - muY) * T + muX;
else
    Z = (Y - muY) * T + muX;
end
res = X - Z;
d = sum(res(:).^2) / max(ssX, eps);
transform = struct('T', T, 'b', b, 'c', muX - b * muY * T);
end
