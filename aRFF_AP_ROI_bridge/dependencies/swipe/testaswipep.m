% test A-SWIPE'

minF0 = 75;
maxF0 = 600;
[y, fs] = audioread('clarinet.wav');
y = 0.9*(y./max(abs(y)));
t = linspace(0, length(y)/fs, length(y));
[P,T,S,PC,s] = aswipep(y, fs, [minF0, maxF0]);
Pi = interp1(T, P, t, 'pchip', NaN);
Si = interp1(T, S, t, 'pchip', NaN);
plot(t, Pi);