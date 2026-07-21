function aRFF = checking_cycles(aRFF,stepsize)

aRFF.peak_array = unique(aRFF.peak_array);
aRFF.trough_array = unique(aRFF.trough_array);

%fix long cycles

f0y_diff = diff(aRFF.f0y(aRFF.trough_array(1):aRFF.trough_array(end)));
f0y_diff = f0y_diff > 0;
trough_pos = strfind(f0y_diff',[0 1]);
trough_pos = trough_pos+aRFF.trough_array(1);
f0y_diff = diff(aRFF.f0y(aRFF.peak_array(1):aRFF.peak_array(end)));
f0y_diff = f0y_diff > 0;
peak_pos = strfind(f0y_diff',[1 0]);
peak_pos = peak_pos+aRFF.peak_array(1);

if strcmp(aRFF.onoff,'off')
    TPrange = min(aRFF.f0y(aRFF.peak_array))-max(aRFF.f0y(aRFF.trough_array));
    maxTval = max(aRFF.f0y(aRFF.trough_array))+TPrange/5;
    minPval = min(aRFF.f0y(aRFF.trough_array))-TPrange/5;
else
    TPrange = min(aRFF.f0y(aRFF.peak_array))-max(aRFF.f0y(aRFF.trough_array));
    maxTval = max(aRFF.f0y(aRFF.trough_array))+TPrange/5;
    minPval = min(aRFF.f0y(aRFF.trough_array))-TPrange/5;
end

localmin = trough_pos(aRFF.f0y(trough_pos) < maxTval);
localmax = peak_pos(aRFF.f0y(peak_pos) > minPval);

diff_trough_array = diff(aRFF.trough_array);
longcyclestart = find(diff(aRFF.trough_array) > 4/3*stepsize);

for longcyclei = 1:length(longcyclestart)
    longcycle = longcyclestart(longcyclei);
    minloc = aRFF.trough_array(longcycle);
    maxloc = aRFF.trough_array(longcycle+1);
    addtrough = find(localmin>minloc & localmin<maxloc);
    numcyclestoadd = min(length(addtrough),ceil((maxloc-minloc)/stepsize));
    if ~isempty(addtrough);
        aRFF.trough_array = [aRFF.trough_array localmin(addtrough(1:numcyclestoadd))];
    end
end
aRFF.trough_array = sort(aRFF.trough_array);
diff_peak_array = diff(aRFF.peak_array);
longcyclestart = find(diff(aRFF.peak_array) > 4/3*stepsize);

for longcyclei = 1:length(longcyclestart)
    longcycle = longcyclestart(longcyclei);
    minloc = aRFF.peak_array(longcycle);
    maxloc = aRFF.peak_array(longcycle+1);
    addpeak = find(localmax>minloc & localmax<maxloc);
    numcyclestoadd = min(length(addpeak),ceil((maxloc-minloc)/stepsize));
    if ~isempty(addpeak);
        aRFF.peak_array = [aRFF.peak_array localmax(addpeak(1:numcyclestoadd))];
    end
end
aRFF.peak_array = sort(aRFF.peak_array);

%fix short cycles

diff_trough_array = diff(aRFF.trough_array);
shortcyclestart = find(diff_trough_array < 2/3*stepsize);
if ~isempty(shortcyclestart)
    minshort = min(shortcyclestart);
    maxshort = max(shortcyclestart);
    doublepeaksec = aRFF.trough_array(minshort)-ceil(stepsize/4):aRFF.trough_array(maxshort)+floor(stepsize/4);
    smoothf0y =  smooth(aRFF.f0y(doublepeaksec),ceil(stepsize/2));
    smoothf0y_diff = diff(smoothf0y) > 0;
    trough_pos = strfind(smoothf0y_diff(ceil(stepsize/4)+1:end - floor(stepsize/4))',[0 1]);
    trough_pos = trough_pos+aRFF.trough_array(minshort);
    if all(abs(diff(trough_pos) - stepsize)/stepsize < 1/3)
        aRFF.trough_array(minshort:maxshort) = [];
        aRFF.trough_array = sort([aRFF.trough_array trough_pos]);
    end
end

diff_peak_array = diff(aRFF.peak_array);
shortcyclestart = find(diff_peak_array < 2/3*stepsize);
if ~isempty(shortcyclestart)
    minshort = min(shortcyclestart);
    maxshort = max(shortcyclestart);
    doublepeaksec = aRFF.peak_array(minshort)-ceil(stepsize/4):aRFF.peak_array(maxshort)+floor(stepsize/4);
    smoothf0y =  smooth(aRFF.f0y(doublepeaksec),ceil(stepsize/2));
    smoothf0y_diff = diff(smoothf0y) > 0;
    peak_pos = strfind(smoothf0y_diff(ceil(stepsize/4)+1:end - floor(stepsize/4))',[1 0]);
    peak_pos = peak_pos+aRFF.peak_array(minshort);
    if all(abs(diff(peak_pos) - stepsize)/stepsize < 1/3)
        aRFF.peak_array(minshort:maxshort) = [];
        aRFF.peak_array = sort([aRFF.peak_array peak_pos]);
    end
end

%check for peaks between troughs
for troughi = 1:length(aRFF.trough_array)-1
    starttrough = aRFF.trough_array(troughi);
    endtrough = aRFF.trough_array(troughi+1);
    if sum(aRFF.peak_array > starttrough & aRFF.peak_array < endtrough)
    else
        [a,add_on_cycle] = max(aRFF.f0y(starttrough:endtrough));
        add_on_cycle = add_on_cycle + starttrough - 1;
        aRFF.peak_array = [aRFF.peak_array add_on_cycle];
        aRFF.peak_array = sort(aRFF.peak_array);
    end
end

%check for troughs between peaks
for peaki = 1:length(aRFF.peak_array)-1
    startpeak = aRFF.peak_array(peaki);
    endpeak = aRFF.peak_array(peaki+1);
    if sum(aRFF.trough_array > startpeak & aRFF.trough_array < endpeak)
    else
        [a,add_on_cycle] = min(aRFF.f0y(startpeak:endpeak));
        add_on_cycle = add_on_cycle + startpeak - 1;
        aRFF.trough_array = [aRFF.trough_array add_on_cycle];
        aRFF.trough_array = sort(aRFF.trough_array);
    end
end


%delete instances with aperiodic cycles.
if strcmp(aRFF.onoff,'off')
    if aRFF.peak_array(end) < aRFF.trough_array(end)
        Tcycles = aRFF.y(aRFF.trough_array(end)-2*stepsize:aRFF.trough_array(end));
        Fcycles = aRFF.y(aRFF.trough_array(end)+1*stepsize:aRFF.trough_array(end)+3*stepsize);
    else
        Tcycles = aRFF.y(aRFF.peak_array(end)-2*stepsize:aRFF.peak_array(end));
        Fcycles = aRFF.y(aRFF.peak_array(end)+1*stepsize:aRFF.peak_array(end)+3*stepsize);
    end
else
    if aRFF.peak_array(1) < aRFF.trough_array(1)
        Tcycles = aRFF.y(aRFF.peak_array(1):aRFF.peak_array(1)+2*stepsize);
        Fcycles = aRFF.y(aRFF.peak_array(1)-3*stepsize:aRFF.peak_array(1)-1*stepsize);
    else
        Tcycles = aRFF.y(aRFF.trough_array(1):aRFF.trough_array(1)+2*stepsize);
        Fcycles = aRFF.y(aRFF.trough_array(1)-3*stepsize:aRFF.trough_array(1)-1*stepsize);
    end
end
[acfF,lags,bounds] = autocorr(Fcycles,round(stepsize*1.5));
maxF = max(acfF(round(stepsize*0.5):round(stepsize*1.5)));
Fcycle_amp = range(Fcycles)/range(Tcycles);
if strcmp(aRFF.onoff,'off')
    if (Fcycle_amp > 0.5 & maxF > 0.5) 
        'reject off'
        aRFF.trough_array = [];
        aRFF.peak_array = [];
        return;
    end
else
    if (Fcycle_amp > 1.0 & maxF > 0.5) 
        'reject on'
        aRFF.trough_array = [];
        aRFF.peak_array = [];
        return;
    end
end

%remove deflections. The range of the cycle closest to
% the consonant is compared to range of the amplitude at the peaks. If there
% were deflection in the waveform in the first few cycles, then the former
% will tend to be smaller than the latter.
peakrange = range(aRFF.y(aRFF.peak_array));
troughrange = range(aRFF.y(aRFF.trough_array));
if strcmp(aRFF.onoff,'off')
    lastpeakcyclerange = range(aRFF.y(aRFF.peak_array(1):aRFF.peak_array(2)));
    lasttroughcyclerange = range(aRFF.y(aRFF.trough_array(1):aRFF.trough_array(2)));
else
    lastpeakcyclerange = range(aRFF.y(aRFF.peak_array(end-1):aRFF.peak_array(end)));
    lasttroughcyclerange = range(aRFF.y(aRFF.trough_array(end-1):aRFF.trough_array(end)));
end
if (peakrange > lastpeakcyclerange) & (troughrange > lasttroughcyclerange)
    aRFF.trough_array = [];
    aRFF.peak_array = [];
    return;
end

