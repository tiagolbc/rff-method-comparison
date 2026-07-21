function [ peak_l ] = peak_find(aRFF, Pbackpulse, Pendbackpulse)
%This function is used to determine a peak in the waveform
%aRFF.f0y. Initially, a maximum is found between Pbackpulse (the timing of
%the left pulse) to Pendbackpulse (the timing of the right pulse). If the
%maximum lies in the edge of the cycle, the algorithm extends the search, 
%continuing outside of the bounds until it finds the peak. It returns
%the location of the peak.

Pcycle_samp = Pbackpulse:Pendbackpulse;
[peak_v, peak_l] = max(aRFF.f0y(Pcycle_samp));
%if the maximum is on the left pulse of an offset cycle, keep searching to the left, until a peak is found 
if (peak_l == 1) & strcmp(aRFF.onoff,'off')
    old_loc = Pcycle_samp(1);
    new_loc = old_loc - 1;
    while aRFF.f0y(new_loc) >= aRFF.f0y(old_loc)
        old_loc = new_loc;
        new_loc = old_loc - 1;
        if (new_loc < aRFF.recordingedge)
            peak_l = peak_l + Pbackpulse - 1;
            return;
        end
        peak_l = peak_l - 1;
    end
end

%if the maximum is on the right pulse of an onset cycle, keep searching to the right, until a peak is found 
if (peak_l == length(Pcycle_samp)) & strcmp(aRFF.onoff,'on')
    old_loc = Pcycle_samp(end);
    new_loc = old_loc + 1;
    while aRFF.f0y(new_loc) >= aRFF.f0y(old_loc)
        old_loc = new_loc;
        new_loc = old_loc + 1;
        if (new_loc > aRFF.recordingedge)
            peak_l = peak_l + Pbackpulse - 1;
            return;
        end
        peak_l = peak_l + 1;
    end
end
 peak_l = peak_l + Pbackpulse - 1;