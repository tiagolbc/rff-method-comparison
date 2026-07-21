function [aRFF] = calcRFF(aRFF)

if strcmp(aRFF.onoff,'off')
    if length(aRFF.peak_array) > 10
        off_t = abs(diff(aRFF.peak_array/aRFF.fs));
        off_f0 = 1./off_t;
        aRFF.peak_RFF_Hz = off_f0;
        aRFF.peak_RFF = 12*log2(off_f0./off_f0(end-9));
        aRFF.peak_RFF_meanf0 = 12*log2(off_f0./aRFF.f0);
    else
        aRFF.peak_RFF_Hz = nan;
        aRFF.peak_RFF = nan;
        aRFF.peak_RFF_meanf0 = nan;
    end
    if length(aRFF.trough_array) > 10
        off_t = abs(diff(aRFF.trough_array/aRFF.fs));
        off_f0 = 1./off_t;
        aRFF.trough_RFF_Hz = off_f0;
        aRFF.trough_RFF = 12*log2(off_f0./off_f0(end-9));
        aRFF.trough_RFF_meanf0 = 12*log2(off_f0./aRFF.f0);
    else
        aRFF.trough_RFF_Hz = nan;
        aRFF.trough_RFF = nan;
        aRFF.trough_RFF_meanf0 = nan;
    end
else
    if length(aRFF.peak_array) > 10 
        on_t = abs(diff(aRFF.peak_array/aRFF.fs));
        on_f0 = 1./on_t;
        aRFF.peak_RFF_Hz = on_f0;
        aRFF.peak_RFF = 12*log2(on_f0./on_f0(10));
        aRFF.peak_RFF_meanf0 = 12*log2(on_f0./aRFF.f0);
    else
        aRFF.peak_RFF_Hz = nan;
        aRFF.peak_RFF = nan;
        aRFF.peak_RFF_meanf0 = nan;
    end
    if length(aRFF.trough_array) > 10
        on_t = abs(diff(aRFF.trough_array/aRFF.fs));
        on_f0 = 1./on_t;
        aRFF.trough_RFF_Hz = on_f0;
        aRFF.trough_RFF = 12*log2(on_f0./on_f0(10));
        aRFF.trough_RFF_meanf0 = 12*log2(on_f0./aRFF.f0);
    else
        aRFF.trough_RFF_Hz = nan;
        aRFF.trough_RFF = nan;
        aRFF.trough_RFF_meanf0 = nan;
    end
end
end

