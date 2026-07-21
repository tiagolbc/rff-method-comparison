function [t0_step,aRFF] = finer_t0_est(lastpulse,aRFF,first_t0_est)
%this function is used to get finer estimate of the period (t0_step). First, it
%takes in the first "cycle" pulse (lastpulse), RFF parameters (aRFF), and
%the initial estimate of the period (first_t0_estimate). 

global min_pitch_set;
global max_pitch_set;

max_auto = 0;
time_delay = 0;
subratio = 0;
subconsis = 0;
half_subconsis = 0;
twice_subconsis = 0;
if aRFF.f0_lb < min_pitch_set
    max_ind = ceil(aRFF.fs/min_pitch_set);
else
    max_ind = ceil(aRFF.fs/aRFF.f0_lb);
end

if aRFF.f0_ub > max_pitch_set
    min_ind = floor(aRFF.fs/max_pitch_set);
else
    min_ind = floor(aRFF.fs/aRFF.f0_ub);
end

while ~(max_auto > 0.7 & subratio)
    if strcmp(aRFF.onoff,'off')
        %if we are close to the edge of the recording, then skip this step
        if lastpulse-round(0.15*aRFF.fs)-round(time_delay*aRFF.fs) < aRFF.recordingedge
            t0_step = first_t0_est;
            return;
        end
        %otherwise, calculate the autocorreation
        auto_y = autocorr(aRFF.f0y(lastpulse-round(0.15*aRFF.fs)-round(time_delay*aRFF.fs):lastpulse-round(time_delay*aRFF.fs)),2*max_ind);
    else
        if lastpulse+round(time_delay*aRFF.fs)+round(0.15*aRFF.fs) > aRFF.recordingedge
            t0_step = first_t0_est;
            return;
        end
        auto_y = autocorr(aRFF.f0y(lastpulse+round(time_delay*aRFF.fs):lastpulse+round(time_delay*aRFF.fs)+round(0.15*aRFF.fs)),2*max_ind);
    end
    %find the max of the autocorrelation. the location of ind_auto is related to the estimated T0.
    [max_auto,ind_auto] = max(auto_y(min_ind:max_ind));
    
    % if there is a harmonic that has a amplitude that is 95% of
    % amplitude of T0, then set max_auto to 0, so we can time shift the
    % waveform and re-estimate F0
    cropped_region = auto_y(1:ind_auto+min_ind-1) - max_auto*0.95;
    cropped_region = (cropped_region > 0);
    if length(strfind(cropped_region',[0 1])) > 2
        max_auto = 0;
    end
    
    time_delay = time_delay + 0.05;
    
    %look at the amplitude of autocorrelation at twice the estimate T0 and
    %that at half the estimated T0
    halfamp = auto_y(round((ind_auto + min_ind-1)/2));
    twiceamp = auto_y(2*(ind_auto + min_ind-1));
    if (halfamp > twiceamp) & (max_auto > 0.7)
        half_subconsis = half_subconsis + 1;
    elseif (halfamp < twiceamp) & (max_auto > 0.7)
        twice_subconsis = twice_subconsis + 1;
    end
    subconsis = abs(half_subconsis - twice_subconsis);
    subratio = (abs(twiceamp - halfamp) > 0.3) | (subconsis >= 3);
    if time_delay > 1
        % if time delay is exceeded, we will go with the one that happens
        % more often
        if half_subconsis > twice_subconsis
            twiceamp = -1;
        elseif half_subconsis < twice_subconsis
            twiceamp = 1;
        end
        break;
    end
end

if twiceamp > halfamp
    t0_step = round(ind_auto + min_ind-1);
else
    t0_step = round((ind_auto + min_ind-1)/2);
end