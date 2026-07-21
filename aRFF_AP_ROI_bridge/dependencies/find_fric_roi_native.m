function [] = find_fric_roi_native(audiofolname,filename,bridge_manifest)
% ROI input adapter for the original aRFF-AP fricative preparation stage.
%
% The automatic fricative peak search and the interactive correction dialog
% are replaced by externally supplied FricStart/FricEnd values.  The original
% vowel-probability screening, F0/PS aggregation, F0-band filtering, and
% inter-instance recording-edge calculations are retained below.

global min_pitch_set;
global max_pitch_set;
global maxpkn;
global perform_fol;

% Initializing the original AP working variables.
v1_y_array = []; %array for offset vowel
v2_y_array = []; %array for onset vowel
offset_F0  = [];
onset_F0   = [];
offset_PS  = [];
onset_PS   = [];

%declaring subject folders
aRFF.subjectid = filename(1:end-4);
VCV = filename(end-6:end-4);
folname  = fullfile(perform_fol,aRFF.subjectid,'var');
fricfile = fullfile(folname,'fric_param.mat');
f0cfile  = fullfile(folname,'f0c_param.mat'); % F0 contour variables

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
[aRFF.y,aRFF.fs] = audioread(fullfile(audiofolname,filename));
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

v_prob_temp = v_prob;

max_ind = ceil(aRFF.fs/min_pitch_set);
min_ind = floor(aRFF.fs/max_pitch_set);

% Read and order the externally supplied ROIs for this working audio file.
roi_rows = bridge_manifest(strcmp(string(bridge_manifest.BridgeFilename),string(filename)),:);
if isempty(roi_rows)
    error('No ROI rows found for %s.',filename);
end
[~,roi_order] = sort(double(roi_rows.FricStart));
roi_rows = roi_rows(roi_order,:);
FricStart = double(roi_rows.FricStart(:));
FricEnd = double(roi_rows.FricEnd(:));
if any(~isfinite(FricStart)) || any(~isfinite(FricEnd)) || any(FricEnd <= FricStart)
    error('Invalid FricStart/FricEnd values for %s.',filename);
end
totalinst = height(roi_rows);
fric_start_loc = max(1,min(t_len,round(FricStart.*aRFF.fs)));
fric_end_loc = max(1,min(t_len,round(FricEnd.*aRFF.fs)));
pk_loc = round((fric_start_loc+fric_end_loc)./2)';
pk_mag = nan(1,totalinst); % No automatic fricative score in ROI mode.
offpitch = zeros(1,totalinst);
onpitch = zeros(1,totalinst);
offps = zeros(1,totalinst);
onps = zeros(1,totalinst);
roi_vowel_gate_pass = false(totalinst,1);

for pki = 1:totalinst
    % Original AP uses 250-ms vowel contexts.  With an interval ROI, the
    % offset context ends at FricStart and the onset context begins at
    % FricEnd; samples inside the fricative are never used as vowel data.
    f_front_time_frame = max(1,round(fric_start_loc(pki)-aRFF.fs/4)):max(1,fric_start_loc(pki)-1);
    f_back_time_frame = min(t_len,fric_end_loc(pki)+1):min(t_len,round(fric_end_loc(pki)+aRFF.fs/4));
    if isempty(f_front_time_frame) || isempty(f_back_time_frame)
        continue;
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
        
        roi_vowel_gate_pass(pki) = true;
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
fric_start_loc = fric_start_loc(pk_locind);
fric_end_loc = fric_end_loc(pk_locind);
FricStart = FricStart(pk_locind);
FricEnd = FricEnd(pk_locind);
roi_vowel_gate_pass = roi_vowel_gate_pass(pk_locind);
roi_rows = roi_rows(pk_locind,:);
totalinst = length(pk_loc);

%combine all vowels and estimate F0 to create F0y. The concatenated vowels
%will be sliced into 50 ms chucks, where the pitch will be estimated from
%each chunk.

vowel_array = [v1_y_array; v2_y_array];
F0s = [offset_F0; onset_F0];
cutamount = round(.05*aRFF.fs);
numSlice = floor(length(vowel_array)/cutamount);

F0_tracker = [];
for vowelamounti = 1:numSlice
    startvowel = (vowelamounti-1)*cutamount+1;
    endvowel = vowelamounti*cutamount;
    F0s_slice = F0s(startvowel:endvowel);
    F0_tracker(vowelamounti) = mean(F0s_slice); %#ok<AGROW>
end
if isempty(F0_tracker)
    % The original code cannot form a 50-ms pitch slice in this situation.
    % Retain the ROI instance but let the downstream native output classify
    % it as unavailable rather than substituting another detector.
    F0_tracker = F0s(isfinite(F0s) & F0s > 0);
end
if isempty(F0_tracker)
    error('aRFF-AP could not obtain vowel F0 evidence for %s.',filename);
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

% pk_loc remains the midpoint of each external ROI.  The automatic
% minimum-search refinement and manual GUI are intentionally bypassed.

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
roi_metadata = roi_rows;
roi_adapter = struct('version','v16','policy','external FricStart/FricEnd only', ...
    'offset_anchor','FricStart','onset_anchor','FricEnd', ...
    'automatic_fricative_detection',false,'vowel_gate_pass',roi_vowel_gate_pass);
save(fricfile,'aRFF','v_prob','f_prob','pk_loc','totalinst','offedge','onedge', ...
    'offpitch','onpitch','offps','onps','fric_start_loc','fric_end_loc', ...
    'FricStart','FricEnd','roi_metadata','roi_adapter')

close all;
end

