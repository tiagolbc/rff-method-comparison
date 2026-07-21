function [] = find_fric_aswipep(audiofolname,filename)
%This function is used to determine the locations of fricatives.

global min_pitch_set;
global max_pitch_set;
global maxpkn;
global perform_fol;

%initializing variables. Do not change.
pki = 1;
v1_y_array = []; %array for offset vowel
v2_y_array = []; %array for onset vowel
offset_F0  = [];
onset_F0   = [];
offset_PS  = [];
onset_PS   = [];
totalinst = maxpkn;

%declaring subject folders
aRFF.subjectid = filename(1:end-4);
VCV = filename(end-6:end-4);
folname  = [perform_fol aRFF.subjectid '\var\'];
fricfile = [folname 'fric_param.mat'];
f0cfile  = [folname 'f0c_param.mat']; % F0 contour variables

% if f0cfile doesn't exist, create it; otherwise, load it in
if exist(f0cfile,'file')
    load(f0cfile);
else
    find_contours_aswipep(audiofolname, filename) 
    load(f0cfile);
end

%creating subject folders
if ~exist(folname,'dir')
    mkdir(folname);
end

%read in audio file. If there are multiple channels, read first channel
[aRFF.y,aRFF.fs] = audioread([audiofolname filename]);
aRFF.t = 0:1/aRFF.fs:(length(aRFF.y) - 1)/aRFF.fs;
if size(aRFF.y,2) > 1
    aRFF.y = aRFF.y(:,1);
end
t_len = length(aRFF.t);

%peak normalize audio file
aRFF.y = (aRFF.y)./max(abs(aRFF.y));

%make sure F0c is in correct orientation (column vector)
if size(aRFF.F0c,2) > 1
    aRFF.F0c = aRFF.F0c';
end

%v_prob is high there is likely to be a vowel. It is related to the amount
%of energy in 0 - 3.4 kHz.
[B,A] = butter(5,(3400)/(aRFF.fs/2),'low');
lowy = filtfilt(B,A,aRFF.y);
sm_lowy = smooth(abs(lowy),aRFF.fs/20);
v_prob = (sm_lowy-mean(sm_lowy))./std(sm_lowy);
v_prob = v_prob - min(v_prob);

%f_prob is high when there is likely to be a fricative. It is related to
%the amount of energy in 3.4 kHz to 8 kHz.
[B,A] = butter(5,[(3400)/(aRFF.fs/2) (8000)/(aRFF.fs/2)]);
highy = filtfilt(B,A,aRFF.y);
sm_highy = smooth(abs(highy),aRFF.fs/20);
fric_like = smooth(sm_highy./sm_lowy,aRFF.fs/20);
f_prob = (fric_like-mean(fric_like))./std(fric_like);
f_prob = f_prob - min(f_prob);

fv_diff_prob_temp = f_prob - v_prob;
fv_diff_prob_temp = smooth(fv_diff_prob_temp,aRFF.fs/20);
v_prob_temp = v_prob;

max_ind = ceil(aRFF.fs/min_pitch_set);
min_ind = floor(aRFF.fs/max_pitch_set);

%identify the peaks in the fv_diff_prob_temp
while (pki < totalinst+1)
    %finding peaks for fricative
    if max(fv_diff_prob_temp) == 0
        [pk_mag(pki),pk_loc(pki)] = max(-1*fv_diff_prob_temp);
    else  
        [pk_mag(pki),pk_loc(pki)] = max(fv_diff_prob_temp);
    end
    %this is the time frame from 250 ms to 250 ms after the fricative
    f_time_frame = max(1,round(pk_loc(pki)-aRFF.fs/4)):min(t_len,round(pk_loc(pki)+aRFF.fs/4));
    %this is the time frame from 250 ms before to the fricative
    f_front_time_frame = max(1,round(pk_loc(pki)-aRFF.fs/4)):pk_loc(pki);
    %this is the time frame from the fricative to 250 ms after
    f_back_time_frame = pk_loc(pki):min(t_len,round(pk_loc(pki)+aRFF.fs/4));
    %temporary set to 0, so that no other peaks will be detected from this VCV instance. This assumes that the fricative should last no more than 500 ms.
    fv_diff_prob_temp(f_time_frame) = 0;
    
    %if the peak of fv_diff_prob_temp is less than a certain thresh, then
    %delete
    if any((pk_mag./max(pk_mag)) < 0.5)
        pk_mag(end) = [];
        pk_loc(end) = [];
        break;
    end
    
    %finding the peak and mean for in the v_prob_temp during
    %f_front_time_frame and f_back_time_frame. The former should be high if
    %this location contains an offset vowel. THe latter should be high if
    %this location contains an onset vowel.
    v1mean = mean(v_prob_temp(f_front_time_frame));
    v2mean = mean(v_prob_temp(f_back_time_frame));
    [v1max,v1_ind] = max(v_prob_temp(f_front_time_frame));
    [v2max,v2_ind]= max(v_prob_temp(f_back_time_frame));
    
    %decide if this is a valid VCV instance by checking whether the potential vowel
    %max and mean passes a certain threshold
    if v1max > 0.4 & v2max > 0.4 & v1mean > 0.15 & v2mean > 0.15
        v1_y = aRFF.y(f_front_time_frame);
        F0_off = aRFF.F0c(f_front_time_frame);
        PS_off = aRFF.PSc(f_front_time_frame);
        
        v2_y = aRFF.y(f_back_time_frame);
        F0_on = aRFF.F0c(f_back_time_frame);
        PS_on = aRFF.PSc(f_back_time_frame);
        
        %clear the locations where the v_prob_temp is low, because this is
        %likely not a portion of the vowel and might not be useful for
        %the initial estimate of the vowel's pitch.
        v1_y(v_prob_temp(f_front_time_frame)<1) = [];
        F0_off(v_prob_temp(f_front_time_frame)<1) = [];
        PS_off(v_prob_temp(f_front_time_frame)<1) = [];
        
        v2_y(v_prob_temp(f_back_time_frame)<1) = [];
        F0_on(v_prob_temp(f_back_time_frame)<1) = [];
        PS_on(v_prob_temp(f_back_time_frame)<1) = [];
        
        v1_y_array = [v1_y_array; v1_y];
        v2_y_array = [v2_y_array; v2_y];
        
        offset_F0 = [offset_F0; F0_off];
        onset_F0  = [onset_F0; F0_on];   
        
        offset_PS = [offset_PS; PS_off'];
        onset_PS  = [onset_PS; PS_on'];   
        
        v1_array_end(pki) = length(v1_y_array);
        v2_array_end(pki) = length(v2_y_array);

        offset_F0_array_end(pki) = length(offset_F0);
        onset_F0_array_end(pki) = length(onset_F0);

        offset_PS_array_end(pki) = length(offset_PS);
        onset_PS_array_end(pki) = length(onset_PS);
        
        % If offset vowel is long enough, estimate F0 from offset vowel
        if length(v1_y) > max_ind
            offpitch(pki) = mean(F0_off);
            offps(pki) = mean(PS_off);
        else
            offpitch(pki) = 0;
            offps(pki) = 0;
        end
        
        % If the onset vowel is long enough, estimate F0 from onset vowel
        if length(v2_y) > max_ind
            onpitch(pki) = mean(F0_on);
            onps(pki) = mean(PS_on);
        else
            onpitch(pki) = 0;
            onps(pki) = 0;
        end
        
        pki = pki+1;
    end
    
    %In rare cases, there may be multiple peaks in the fv_diff_prob_temp.
    %For example, suppose these are four peaks in fv_diff_prob_temp. What
    %we want to do is to make sure to get the fourth peak (and we know that
    %there's a fourth peak because the heigh of the fourth peak is higher
    %than 80% of the height of the third peak) is captures so we can decide
    %on which peak to take later.
    
    if (pki == totalinst+1) && (max(fv_diff_prob_temp) > min(pk_mag)*0.8)
        totalinst = totalinst + 1;
    end
end

%if we do find more than 3 peaks (potential fricatives), then we decide which ones to take based
%on the the magnitude of the waveform that has been band-passed from 7.5 to
%8.0 kHz, because we know that the instances all utilize the phoneme /f/
%and the mean peak frequency of labiodental fricatives is 7733 Hz. We will
%accept the peaks with the highest sm_highy1 in the peaks locations.
if length(pk_loc) > maxpkn
    [B,A] = butter(5,[(7500)/(aRFF.fs/2) (8000)/(aRFF.fs/2)]);
    highy = filtfilt(B,A,aRFF.y);
    sm_highy1 = smooth(abs(highy),aRFF.fs/20);
    [sm_highy1_pk,sortloc] =  sort(sm_highy1(pk_loc),'descend');
    
    pk_mag(sortloc(maxpkn+1:end)) = [];
    pk_loc(sortloc(maxpkn+1:end)) = [];
    offpitch(sortloc(maxpkn+1:end)) = [];
    onpitch(sortloc(maxpkn+1:end)) = [];
    offps(sortloc(maxpkn+1:end)) = [];
    onps(sortloc(maxpkn+1:end)) = [];
    %delete the incorrect "vowel" data collected
    % offsets
    for delloc = sort(sortloc(maxpkn+1:end)','descend')
        v1_endloc = v1_array_end(delloc);
        if delloc == 1
            v1_startloc = 1;
        else
            v1_startloc = v1_array_end(delloc-1)+1;
        end
        if v1_startloc >= v1_endloc
            continue;
        end
        v1_y_array(v1_startloc:v1_endloc) = [];
        offset_F0(v1_startloc:v1_endloc) = [];
        offset_PS(v1_startloc:v1_endloc) = [];
    end
    % onsets
    for delloc = sort(sortloc(maxpkn+1:end)','descend')
        v2_endloc = v2_array_end(delloc);
        if delloc == 1
            v2_startloc = 1;
        else
            v2_startloc = v2_array_end(delloc-1)+1;
        end
        if v2_startloc >= v2_endloc
            continue;
        end
        v2_y_array(v2_startloc:v2_endloc) = [];
        onset_F0(v2_startloc:v2_endloc) = [];
        onset_PS(v2_startloc:v2_endloc) = [];
    end
end

if length(v1_y_array) > max_ind
    offpitch(offpitch==0) = mean(offset_F0);
    offps(offps==0) = mean(offset_PS);
end
if length(v2_y_array) > max_ind
    onpitch(onpitch==0) = mean(onset_F0);
    onps(onps==0) = mean(onset_PS);
end


%sorting
[pk_loc,pk_locind] = sort(pk_loc);
offpitch = offpitch(pk_locind);
onpitch = onpitch(pk_locind);
offps = offps(pk_locind);
onps = onps(pk_locind);
totalinst = length(pk_loc);

%combine all vowels and estimate F0 to create F0y. The concatenated vowels
%will be sliced into 50 ms chucks, where the pitch will be estimated from
%each chunk.

vowel_array = [v1_y_array; v2_y_array];
F0s = [offset_F0; onset_F0];
cutamount = round(.05*aRFF.fs);
numSlice = floor(length(vowel_array)/cutamount);

for vowelamounti = 1:numSlice
    startvowel = (vowelamounti-1)*cutamount+1;
    endvowel = vowelamounti*cutamount;
    
    F0s_slice = F0s(startvowel:endvowel);
    F0_tracker(vowelamounti) = mean(F0s_slice);
end

aRFF.f0 = mean(F0_tracker);
offpitch(offpitch==0) = aRFF.f0;
onpitch(onpitch==0) = aRFF.f0;
offps(offps==0) = aRFF.ps;
onps(onps==0) = aRFF.ps;

%aRFF.f0y = band-pass filtering acoustic signal based on 3 ST above and below the
%maximum and minimum pitch
aRFF.f0_ub = max(F0_tracker)*2^(3/12);
aRFF.f0_lb = min(F0_tracker)*2^(-3/12);
if aRFF.f0_lb == 0 
    aRFF.f0_lb = 0.01;
end
[B,A] = ellip(2,0.5,100,[(aRFF.f0_lb)/(aRFF.fs/2) (aRFF.f0_ub)/(aRFF.fs/2)]);
aRFF.f0y = filtfilt(B,A,aRFF.y);
aRFF.t0 = round(aRFF.fs/aRFF.f0); %average cycle length in samples.

%adjust the potential location of fricatives (pk_loc). The smooth_f0y tends
%to be high during vowels and low during fricatives, so pk_loc is shifted until it reaches a local minima.
smooth_f0y = smooth(abs(aRFF.f0y),(aRFF.fs/20));
for pk_loci = 1:length(pk_loc)
    currentloc = pk_loc(pk_loci);
    while (currentloc+1 <= length(smooth_f0y)) && (smooth_f0y(currentloc) > smooth_f0y(currentloc+1))
        currentloc = currentloc + 1;
    end
    while (currentloc - 1 >= 1) && (smooth_f0y(currentloc) > smooth_f0y(currentloc-1))
        currentloc = currentloc - 1;
    end
    pk_loc(pk_loci) = currentloc;
end

%users turn to adjust pk_loc. Plotting figure
figure('units','normalized','outerposition',[0 0 1 1], 'name', filename); hold all;
plot(aRFF.t,aRFF.y)
l2 = plot(aRFF.t(pk_loc),aRFF.y(pk_loc),'.','MarkerSize',25);
xlabel('Time (s)')
ylabel('Audio Waveform')
axis tight
title('The large green dots indicate where the program thinks the fricatives are. Please click Ok if it is correct. Otherwise, click No.')

okx = range(aRFF.t)*0.85;
oky = range(aRFF.y)*0.85 + min(aRFF.y);
okwx = range(aRFF.t)*0.1;
okwy = range(aRFF.y)*0.1;
rectangle('Position',[okx,oky,okwx,okwy],'FaceColor','g')
textx = okx +0.5*okwx;
texty = oky +0.5*okwy;
text(textx,texty,'OK!','FontSize',20,'HorizontalAlignment','center');

nox = range(aRFF.t)*0.05;
rectangle('Position',[nox,oky,okwx,okwy],'FaceColor','r')
textx = nox +0.5*okwx;
texty = oky +0.5*okwy;
text(textx,texty,'No!','FontSize',20,'HorizontalAlignment','center');

audiox = range(aRFF.t)*0.9;
audioy = range(aRFF.y)*0.05 + min(aRFF.y);
audiowx = range(aRFF.t)*0.05;
audiowy = range(aRFF.y)*0.05;
rectangle('Position',[audiox,audioy,audiowx,audiowy],'FaceColor','y');
textx = audiox +0.5*audiowx;
texty = audioy +0.5*audiowy;
text(textx,texty,'Audio','FontSize',15,'HorizontalAlignment','center')

%collect user input
[x,y] = ginput(1);

while ~((x > okx) & (x<(okx+okwx)) & (y > oky) & (y<(oky+okwy))) % ~ click ok
    if ((x > nox) & (x<(nox+okwx)) & (y > oky) & (y<(oky+okwy))) % click no
        delete(l2)
        title('Please click to indicate the locations of fricatives. Press enter when done.')
        [x,y] = ginput();
        correct_pk_loc = floor(x*length(aRFF.y)/aRFF.t(end));
        totalinst = length(x);
        for current_pk_loci = 1:length(correct_pk_loc)
            if any(abs(correct_pk_loc(current_pk_loci)-pk_loc) < (aRFF.fs*0.025))
                [~,loc] = min(abs(correct_pk_loc(current_pk_loci)-pk_loc) < (aRFF.fs*0.025));
                new_offpitch(current_pk_loci) = offpitch(loc);
                new_onpitch(current_pk_loci) = onpitch(loc);
                new_offps(current_pk_loci) = offps(loc);
                new_onps(current_pk_loci) = onps(loc);
            else
                new_offpitch(current_pk_loci) = mean(offpitch);
                new_onpitch(current_pk_loci) = mean(onpitch);
                new_offps(current_pk_loci) = mean(offps);
                new_onps(current_pk_loci) = mean(onps);
            end
        end
        pk_loc = correct_pk_loc;
        offpitch = new_offpitch;
        onpitch = new_onpitch;
        offps = new_offps;
        onps = new_onps;
        
        title('Here are the new locations. Please click OK to confirm')
        l2 = plot(aRFF.t(pk_loc),aRFF.y(pk_loc),'.','MarkerSize',25)
    elseif ((x > audiox) & (x<(audiox+audiowx)) & (y > audioy) & (y<(audioy+audiowy)))%clicked audio
        soundsc(aRFF.y,aRFF.fs)
        for linei = 0:0.1:aRFF.t(end)
            lineplot = plot([linei linei],[-1 1],'k');
            pause(0.1)
            delete(lineplot)
        end
    end
    [x,y] = ginput(1);
end

% find the start of offset vowels
offedge = [];
onedge = [];
offedge(1) = 1;
for instancek = 2:totalinst
    fourthRange = floor(1/4*(pk_loc(instancek) - pk_loc(instancek-1)));
    spaceSearchStart = pk_loc(instancek-1)+fourthRange;
    spaceSearchEnd = pk_loc(instancek)-fourthRange;
    [minvalue,offedge(instancek)] = min(v_prob(spaceSearchStart:spaceSearchEnd));
    offedge(instancek) = offedge(instancek) + spaceSearchStart - 1;
end

% find the end of onset vowels
for instancek = 1:totalinst-1
    onedge(instancek) = offedge(instancek+1);
end
onedge(totalinst) = length(aRFF.y);

%saving fricative variables to folder
save(fricfile,'aRFF','v_prob','f_prob','pk_loc','totalinst','offedge','onedge','offpitch','onpitch','offps','onps')

close all;
end

