function [trough_l] = trough_find(aRFF, Tbackpulse, Tendbackpulse)
%This function is used to determine a trough in the waveform
%aRFF.f0y. Initially, a minimum is found between Tbackpulse (the timing of
%the left pulse) to Tendbackpulse (the timing of the right pulse). If the
%minimum lies in the edge of the cycle, the algorithm extends the search, 
%continuing outside of the bounds until it finds the trough. It returns
%the location of the trough.

Tcycle_samp = Tbackpulse:Tendbackpulse;
[trough_v, trough_l] = min(aRFF.f0y(Tcycle_samp));

%if the minimum is on the left pulse of an offset cycle, keep searching to the left, until a trough is found 
if (trough_l == 1) & strcmp(aRFF.onoff,'off')  
    old_loc = Tcycle_samp(1);
    new_loc = old_loc - 1;
    while aRFF.f0y(new_loc) <= aRFF.f0y(old_loc)
        old_loc = new_loc;
        new_loc = old_loc - 1;
        if (new_loc < aRFF.recordingedge)
            trough_l = trough_l + Tbackpulse - 1;
            return;
        end
        trough_l = trough_l - 1;
    end
end
%if the minimum is on the right pulse of an onset cycle, keep searching to the right, until a trough is found 
if (trough_l == length(Tcycle_samp)) & strcmp(aRFF.onoff,'on')
    old_loc = Tcycle_samp(end);
    new_loc = old_loc + 1;
    while aRFF.f0y(new_loc) <= aRFF.f0y(old_loc)
        old_loc = new_loc;
        new_loc = old_loc + 1;
        if (new_loc > aRFF.recordingedge)
            trough_l = trough_l + Tbackpulse - 1;
            return;
        end
        trough_l = trough_l + 1;
    end
end
trough_l = trough_l + Tbackpulse - 1;