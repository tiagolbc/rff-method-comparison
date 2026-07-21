function count = zero_crossings(x)
% Count the number of zero-crossings from the supplied time-domain
% input vector.  A simple method is applied here that can be easily
% ported to a real-time system that would minimize the number of
% if-else conditionals.
%
% Usage:     COUNT = zero_crossings(X);
%
%            X     is the input time-domain signal (one dimensional)
%            COUNT is the amount of zero-crossings in the input signal
%
% Author:    sparafucile17 06/27/04
%

% initial value
count = 0;

% error checks
if(length(x) == 1)
    error('ERROR: input signal must have more than one element');
end

if((size(x, 2) ~= 1) && (size(x, 1) ~= 1))
    error('ERROR: Input must be one-dimensional');
end
   
% force signal to be a vector oriented in the same direction
x = x(:);

num_samples = length(x);
for i=2:num_samples

    x_sign          = sign(x);             % Negative: -1, Zero: 0, Positive 1
    index_0         = find(x_sign == 0);   % Index of elements == 0
    x_sign(index_0) = 1;                   % Set elements == 0 to 1
    x_sign_diff     = diff(x_sign);        % Change of sign detection
    count = length(find(x_sign_diff ~= 0)); % Not == 0 means a jump of sign
   
end