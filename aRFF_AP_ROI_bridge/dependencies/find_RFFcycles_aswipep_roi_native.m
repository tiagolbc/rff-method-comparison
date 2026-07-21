function [] = find_RFFcycles_aswipep_roi_native(audiofolname,filename,figplot)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% FIND_RFFCYCLES_ASWIPEP.M finds RFF cycles when using Auditory-SWIPE' to 
% estimate fundamental frequency
%
% Author: Jenny Vojtech (jmvo@bu.edu)
%         Stepp Lab, Boston University, MA
% Last Updated: 11/11/2018
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
clear aRFF;
close all;

global perform_fol;
global min_pitch_set;
global max_pitch_set;

%declaring subject folders
aRFF.subjectid = filename(1:end-4);
folname = fullfile(perform_fol,aRFF.subjectid,'var');
fricfile = fullfile(folname,'fric_param.mat');

%if we do not have the fricfile, need to go back and create it
if ~exist(fricfile,'file')
    find_fric_aswipep(audiofolname, filename)
    return;
else
    load(fricfile);
end

diff_prob = smooth(f_prob - v_prob,round(aRFF.fs/20));

%plot audio waveform and processed signals
if figplot
    figure('units','normalized','outerposition',[0 0 1 1],'visible','off');
    subplot(4,1,1);
    hold on;
    plot(aRFF.t,aRFF.y);
    xlabel('Time (s)')
    ylabel('Audio Waveform (X)')
    hold off;
    subplot(4,1,2);
    hold on;
    plot(aRFF.t,v_prob');
    plot(aRFF.t,f_prob');
    plot(aRFF.t,diff_prob);
    legend('X_{VowelLike}','X_{FricativeLike}','Difference');
    ylabel('Filtered Signal');
    xlabel('Time (s)');
    hold off;
    subplot(4,1,3);
    hold on;
    plot(aRFF.t,aRFF.f0y);
    plot(aRFF.t(pk_loc),aRFF.f0y(pk_loc),'.','MarkerSize',25);
    xlabel('Time (s)');
    ylabel('Filtered Waveform X_{F0}');
    legend('X_{F0}','L_{Fricatives}');
    hold off;
end

%categories and thresholds
load('aRFFparam.mat');

% for each RFF instance, calculate offset RFF, then onset RFF
% save data into performance folder
for instancei = 1:totalinst
    aRFF.instancei = instancei;
    % The only methodological input substitution in this function:
    % OFF is anchored to the external ROI start and ON to the ROI end.
    % All original AP cycle-search, repair, and calcRFF calls remain below.
    fric_center_off = fric_start_loc(aRFF.instancei);
    fric_center_on = fric_end_loc(aRFF.instancei);
    fric_center = fric_center_off;
    
    %% CALCULATE OFFSET RFF
    aRFF.onoff    = 'off';
    aRFF.offpitch = offpitch;
    aRFF.offps    = offps;
    instancefile  = fullfile(folname,[num2str(instancei) '_' aRFF.onoff '.mat']);
    pitchstr      = offps(instancei);
    category      = discretize(pitchstr,[0,off_th,1],0:numel(off_th));
    
    if category > 0
        off_t0_step = round(aRFF.fs/offpitch(instancei)); % average period
        max_acf_range = floor(off_t0_step*1.5);           % maximum period allowed is 1.5*Tavg
        
        % first pulse located at 3Tavg + fricative loc
        % next pulse is Tavg before.
        Tendbackpulse = fric_center + 3*off_t0_step;
        Pendbackpulse = fric_center + 3*off_t0_step;
        Tbackpulse = Tendbackpulse - off_t0_step;
        Pbackpulse = Pendbackpulse - off_t0_step;
        
        aRFF.trough_array     = []; % array of trough samples
        aRFF.peak_array       = []; % array of peak samples
        
        % counters, etc.
        aRFF.peakcyclefull    = 0;  % =1 if we have >=10 peak pulses
        aRFF.troughcyclefull  = 0;  % =1 if we have >=10 trough pulses
        aRFF.PulseFindingDone = 0;  % =1 if quit the while loop
        aRFF.checkedonce      = 0; %ran through checking_cycles at least once
        aRFF.recordingedge    = offedge(aRFF.instancei);
        donewithdeletion      = 0;
        
        % store acoustic features
        trough_nzc_all   = []; % store trough zero crossings (zc)
        peak_nzc_all     = []; % store peak zc
        trough_ptp_all   = []; % store trough peak-to-peak ratios (ptp)
        peak_ptp_all     = []; % store peak ptp
        trough_wss_all   = []; % store trough shape similarity (ss)
        peak_wss_all     = []; % store peak ss
        last_trough_vect = []; % trough vector for last cycle used to calc ss
        last_peak_vect   = []; % peak vector for last cycle used to calc ss
        
        
        while ~aRFF.PulseFindingDone
            % plot and quit if the start of the recording is reached
            if min(Tbackpulse, Pbackpulse) - 1 < aRFF.recordingedge
                if figplot
                    plot_pulses(aRFF)
                end
                break;
            end
            
            trough_l = trough_find(aRFF, Tbackpulse, Tendbackpulse); % cycle trough
            peak_l   = peak_find(aRFF, Pbackpulse, Pendbackpulse);   % cycle peak
            
            % plot and quit if the start of the offset vowel is reached
            if min(trough_l, peak_l) - off_t0_step < aRFF.recordingedge
                if figplot
                    plot_pulses(aRFF)
                end
                break;
            end
            
            cycle_trough_l = trough_l-off_t0_step:trough_l;
            cycle_peak_l   = peak_l-off_t0_step:peak_l;
            
            % compute acoustic parameters for troughs, then peaks
            trough_ptp = range(aRFF.f0y(cycle_trough_l));                   % peak-to-peak amplitude
            troughmean = mean(aRFF.y(cycle_trough_l));                      % local mean
            trough_nzc = zero_crossings(aRFF.y(cycle_trough_l)-troughmean); % zero crossings
            
            if isempty(last_trough_vect) %shape similarity
                trough_wss = 1;
            else
                ptspace    = linspace(1,length(cycle_trough_l),length(last_trough_vect));
                vq         = interp1(1:length(cycle_trough_l),aRFF.y(cycle_trough_l),ptspace);
                trough_wss = procrustes(last_trough_vect,vq','reflection',false);
            end
            
            peak_ptp = range(aRFF.f0y(cycle_peak_l));                 % peak-to-peak amplitude
            peakmean = mean(aRFF.y(cycle_peak_l));                    % local mean
            peak_nzc = zero_crossings(aRFF.y(cycle_peak_l)-peakmean); % zero crossings
            
            if isempty(last_peak_vect) % shape similarity
                peak_wss = 1;
            else
                ptspace  = linspace(1,length(cycle_peak_l),length(last_peak_vect));
                vq       = interp1(1:length(cycle_peak_l),aRFF.y(cycle_peak_l),ptspace);
                peak_wss = procrustes(last_peak_vect,vq','reflection',false);
            end
            
            %storing variables for new troughs or peaks
            if ~ismember(trough_l,aRFF.trough_array)
                aRFF.trough_array = [aRFF.trough_array trough_l];
                trough_nzc_all    = [trough_nzc_all trough_nzc];
                trough_ptp_all    = [trough_ptp_all trough_ptp];
                trough_wss_all    = [trough_wss_all trough_wss];
                last_trough_vect  = aRFF.y(cycle_trough_l);
            end
			if ~ismember(peak_l,aRFF.peak_array)
                aRFF.peak_array = [aRFF.peak_array peak_l];
                peak_nzc_all    = [peak_nzc_all peak_nzc];
                peak_ptp_all    = [peak_ptp_all peak_ptp];
                peak_wss_all    = [peak_wss_all peak_wss];
                last_peak_vect  = aRFF.y(cycle_peak_l);
            end
            
            %if there are at least five pulses and the last six cycles
            %have similar shapes, the try to determine first peak
            if ~donewithdeletion && (length(trough_nzc_all)>5) && (all(trough_wss_all(end-4:end)<0.5))
                long_enough = (aRFF.trough_array(end-4) - aRFF.trough_array(end) + 1) > max_acf_range;
                if ~long_enough
                    Tendbackpulse = peak_l;
                    Tbackpulse    = peak_l - off_t0_step;
                    Pendbackpulse = trough_l;
                    Pbackpulse    = trough_l - off_t0_step;
                    continue;
                end
                acf = autocorr(aRFF.y(aRFF.trough_array(end):aRFF.trough_array(end-4)),max_acf_range);
                maxacf = max(acf(floor(off_t0_step*0.5):max_acf_range));
                if (maxacf>0.7) && ((~diff_prob(Tbackpulse) > diff_prob(Tendbackpulse)) || (sum(trough_wss_all < 0.5) > 10))
                    
                    %find thresholds that maximizes effect size of a vector
                    trough_nzc_thresh = (1+offshiftthresh)*threshfind(trough_nzc_all);
                    trough_ptp_thresh = (1-offshiftthresh)*threshfind(trough_ptp_all);
                    trough_wss_thresh = (1+offshiftthresh)*threshfind(trough_wss_all);
                    peak_nzc_thresh   = (1+offshiftthresh)*threshfind(peak_nzc_all);
                    peak_ptp_thresh   = (1-offshiftthresh)*threshfind(peak_ptp_all);
                    peak_wss_thresh   = (1+offshiftthresh)*threshfind(peak_wss_all);
                    
                    %find indicies that crosses this threshold
                    alltroughfeats = [trough_ptp_all',trough_nzc_all',trough_wss_all'];
                    deltrough_nzc  = find(trough_nzc_all>trough_nzc_thresh,1,'last');
                    deltrough_ptp  = find(trough_ptp_all<trough_ptp_thresh,1,'last');
                    deltrough_wss  = find(trough_wss_all>trough_wss_thresh,1,'last');
                    troughfeats    = {deltrough_ptp, deltrough_nzc, deltrough_wss};
                    
                    allpeakfeats = [peak_ptp_all',peak_nzc_all',peak_wss_all'];
                    delpeak_nzc  = find(peak_nzc_all>peak_nzc_thresh,1,'last');
                    delpeak_ptp  = find(peak_ptp_all<peak_ptp_thresh,1,'last');
                    delpeak_wss  = find(peak_wss_all>peak_wss_thresh,1,'last');
                    peakfeats    = {delpeak_ptp, delpeak_nzc, delpeak_wss};
                    
                    for i = 1:2
                        if i == 1
                            delfeats = peakfeats;
                            feats    = allpeakfeats;
                        else
                            delfeats = troughfeats;
                            feats    = alltroughfeats;
                        end
                        
                        for features = 1:3
                            if ~isempty(delfeats{features})
                                if feats(delfeats{features},features) < off_thresh(category, features)
                                    shift = off_shift(features);
                                else
                                    shift = 0;
                                end
                                delcyc(features) = delfeats{features} + shift;
                            else
                                delcyc(features) = NaN;
                            end
                        end
                        
                        D = delcyc(~isnan(delcyc));
                        deltroughpeakval = round(median(D));
                        
                        if i == 1
                            if deltroughpeakval > numel(aRFF.peak_array)
                                delpeak = numel(aRFF.peak_array);
                            else
                                delpeak = deltroughpeakval;
                                switch category
                                    case {1,2,3}
                                        delpeak = delpeak - 2;
                                    otherwise
                                        delpeak = delpeak - 1;
                                end
                                if delpeak <= 0
                                    delpeak = 1;
                                elseif delpeak > numel(aRFF.peak_array)
                                    delpeak = numel(aRFF.peak_array);
                                end
                            end
                            if max(D) > numel(aRFF.peak_array)
                                delpeakmax = numel(aRFF.peak_array);
                            else
                                delpeakmax = max(D);
                            end
                        else
                            if deltroughpeakval > numel(aRFF.trough_array)
                                deltrough = numel(aRFF.trough_array);
                            else
                                deltrough = deltroughpeakval;
                                switch category
                                    case {1,2,3}
                                        deltrough = deltrough - 2;
                                    otherwise
                                        deltrough = deltrough - 1;
                                end
                                if deltrough <= 0
                                    deltrough = 1;
                                elseif deltrough > numel(aRFF.trough_array)
                                    deltrough = numel(aRFF.trough_array);
                                end
                            end
                            if max(D) > numel(aRFF.trough_array)
                                deltroughmax = numel(aRFF.trough_array);
                            else
                                deltroughmax = max(D);
                            end
                        end
                    end
                    
                    %if the autocorrelation of the waveform between the mid
                    %threshold and the max threshold is less than 0.3, mid
                    %we want to delete up to the max threshold
                    long_enough = (aRFF.trough_array(deltrough) - aRFF.trough_array(deltroughmax) + 1) > max_acf_range;
                    if deltroughmax - deltrough > 3 && long_enough
                        acf    = autocorr(aRFF.y(aRFF.trough_array(deltroughmax):aRFF.trough_array(deltrough)),max_acf_range);
                        maxacf = max(acf(floor(off_t0_step*0.5):max_acf_range));
                        if maxacf < 0.3
                            deltrough = deltroughmax;
                        end
                    end
                    
                    %if the autocorrelation of the waveform between the mid
                    %threshold and the max threshold is less than 0.3, mid
                    %we want to delete up to the max threshold
                    long_enough = (aRFF.peak_array(delpeak) - aRFF.peak_array(delpeakmax) + 1) > max_acf_range;
                    if  delpeakmax - delpeak > 3 && long_enough
                        acf    = autocorr(aRFF.y(aRFF.peak_array(delpeakmax):aRFF.peak_array(delpeak)),max_acf_range);
                        maxacf = max(acf(floor(off_t0_step*0.5):max_acf_range));
                        if maxacf < 0.3
                            delpeak = delpeakmax;
                        end
                    end
                    
                    %if there is nothing to delete, then get more pulses
                    if isnan(deltrough) || isnan(delpeak)
                        Tendbackpulse = peak_l;
                        Tbackpulse    = peak_l - off_t0_step;
                        Pendbackpulse = trough_l;
                        Pbackpulse    = trough_l - off_t0_step;
                        continue;
                    end
                    
                    if min(trough_wss_all) > 0.5
                        deltrough = length(trough_wss_all);
                    end
                    if min(peak_wss_all) > 0.5
                        delpeak = length(peak_wss_all);
                    end
                    
                    %troughtemp and peaktemp should only have pulses where
                    %there are cycles
                    troughtemp              = aRFF.trough_array;
                    peaktemp                = aRFF.peak_array;
                    troughtemp(1:deltrough) = [];
                    peaktemp(1:delpeak)     = [];
                    
                    %re-estimate F0
                    off_t0_step = round(1/aRFF.F0c(Tbackpulse)*aRFF.fs);
                    if off_t0_step > (1/min_pitch_set)*aRFF.fs || off_t0_step < (1/max_pitch_set)*aRFF.fs
                        [off_t0_step,aRFF] = finer_t0_est(Tbackpulse,aRFF,off_t0_step);
                        if off_t0_step > (1/min_pitch_set)*aRFF.fs || off_t0_step < (1/max_pitch_set)*aRFF.fs
                            off_t0_step = round(1/aRFF.offpitch(aRFF.instancei)*aRFF.fs);
                        end
                    end
                    
                    %troughtemp and peaktemp is long enough, then actually
                    %delete the cycles
                    if (length(troughtemp) > 4) && (length(peaktemp) > 4)
                        donewithdeletion               = 1;
                        aRFF.trough_array(1:deltrough) = [];
                        aRFF.peak_array(1:delpeak)     = [];
                    end
                end
            end
            %indicates that there are at least 11 trough cycle pulses
            if length(aRFF.trough_array)>10 && donewithdeletion
                aRFF.troughcyclefull = 1;
            end
            %indicates that there are at least 11 peak cycle pulses
            if length(aRFF.peak_array)>10 && donewithdeletion
                aRFF.peakcyclefull = 1;
            end
            
            if aRFF.peakcyclefull && aRFF.troughcyclefull
                aRFF = checking_cycles(aRFF,off_t0_step); %check cycles
                if isempty(aRFF.trough_array)
                    break;
                end
                if length(aRFF.trough_array) < 11 && length(aRFF.peak_array) < 11
                    break;
                end
                aRFF = calcRFF(aRFF);
                if figplot
                    plot_pulses(aRFF);
                    
                    subplot(4,1,4); hold off;
                    if isfield(aRFF,'trough_RFF_Hz')
                        if ~isnan(aRFF.trough_RFF_Hz)
                            plot(1:10, aRFF.trough_RFF(end-9:end),'.-')
                        else
                            plot(1:10, aRFF.peak_RFF(end-9:end),'.-')
                        end
                    end
                    
                    h = figure(1); %save figure
%                     saveas(h,[folname num2str(instancei) '_' aRFF.onoff '.jpg']);
                end
                aRFF.PulseFindingDone = 1;
            end
            
            Tendbackpulse = peak_l;
            Tbackpulse = peak_l - off_t0_step;
            
            Pendbackpulse = trough_l;
            Pbackpulse = trough_l - off_t0_step;
        end
        save(instancefile,'aRFF');
        
        %clear variables.
        if isfield(aRFF,'trough_RFF_Hz')
            delfields = {'trough_RFF_Hz','peak_RFF_Hz','trough_RFF','peak_RFF','trough_RFF_meanf0','peak_RFF_meanf0'};
            aRFF = rmfield(aRFF,delfields);
        end
    else
        save(instancefile,'aRFF');
    end
    
    %% CALCULATE ONSET RFF
    fric_center = fric_center_on;
    aRFF.onoff   = 'on';
    aRFF.onpitch = onpitch;
    aRFF.onps    = onps;
    instancefile = fullfile(folname,[num2str(instancei) '_' aRFF.onoff '.mat']);
    pitchstr     = onps(instancei);
    category     = discretize(pitchstr,[0,on_th,1],0:numel(on_th));
	
    if category > 0
        on_t0_step  = round(aRFF.fs/onpitch(instancei));
        Tstartpulse = fric_center - 3*on_t0_step;
        Pstartpulse = fric_center - 3*on_t0_step;
        Tfrontpulse = Tstartpulse + on_t0_step;
        Pfrontpulse = Pstartpulse + on_t0_step;
        
        aRFF.peakcyclefull    = 0;
        aRFF.troughcyclefull  = 0;
        aRFF.trough_array     = [];
        aRFF.peak_array       = [];
        aRFF.PulseFindingDone = 0;
        aRFF.checkedonce      = 0;
        aRFF.recordingedge = onedge(aRFF.instancei);
        
        trough_nzc_all   = [];
        peak_nzc_all     = [];
        trough_ptp_all   = [];
        peak_ptp_all     = [];
        last_trough_vect = [];
        last_peak_vect   = [];
        trough_wss_all   = [];
        peak_wss_all     = [];
        donewithdeletion = 0;
        
        while ~aRFF.PulseFindingDone
            if max(Tfrontpulse, Pfrontpulse)+1 > aRFF.recordingedge
                break;
            end
            
            %finding cycle trough
            trough_l = trough_find(aRFF, Tstartpulse, Tfrontpulse);
            
            %finding cycle peak
            peak_l = peak_find(aRFF, Pstartpulse, Pfrontpulse);
            
            if max(peak_l, trough_l) + on_t0_step > aRFF.recordingedge
                break;
            end
            
            cycle_trough_l = trough_l:trough_l+on_t0_step;
            cycle_peak_l   = peak_l:peak_l+on_t0_step;
            
            trough_ptp   = range(aRFF.f0y(cycle_trough_l));
            troughcenter = mean(aRFF.y(cycle_trough_l));
            trough_nzc   = zero_crossings(aRFF.y(cycle_trough_l)-troughcenter);
            
            if isempty(last_trough_vect)
                trough_wss = 1;
            else
                ptspace    = linspace(1,length(cycle_trough_l),length(last_trough_vect));
                vq         = interp1(1:length(cycle_trough_l),aRFF.y(cycle_trough_l),ptspace);
                trough_wss = procrustes(last_trough_vect,vq','reflection',false);
            end
            
            peak_ptp   = range(aRFF.f0y(cycle_peak_l));
            peakcenter = mean(aRFF.y(cycle_peak_l));
            peak_nzc   = zero_crossings(aRFF.y(cycle_peak_l)-peakcenter);
            if isempty(last_peak_vect)
                peak_wss = 1;
            else
                ptspace  = linspace(1,length(cycle_peak_l),length(last_peak_vect));
                vq       = interp1(1:length(cycle_peak_l),aRFF.y(cycle_peak_l),ptspace);
                peak_wss = procrustes(last_peak_vect,vq','reflection',false);
            end
            
            if ~ismember(trough_l,aRFF.trough_array)
                aRFF.trough_array = [aRFF.trough_array trough_l];
                trough_nzc_all = [trough_nzc_all, trough_nzc];
                trough_ptp_all = [trough_ptp_all, trough_ptp];
                trough_wss_all = [trough_wss_all, trough_wss];
                
                last_trough_vect = aRFF.y(cycle_trough_l);
            end
            if ~ismember(peak_l,aRFF.peak_array)
                aRFF.peak_array = [aRFF.peak_array peak_l];
                peak_nzc_all = [peak_nzc_all, peak_nzc];
                peak_ptp_all = [peak_ptp_all, peak_ptp];
                peak_wss_all = [peak_wss_all, peak_wss];
                
                last_peak_vect = aRFF.y(cycle_peak_l);
            end
            
            max_acf_range = floor(on_t0_step*1.5);
            
            if ~donewithdeletion & (length(trough_nzc_all)>5) & (all(trough_wss_all(end-4:end)<0.5))
                long_enough = (aRFF.trough_array(end) - aRFF.trough_array(end-4) + 1) > max_acf_range;
                if ~long_enough
                    Tstartpulse = peak_l;
                    Tfrontpulse = peak_l + on_t0_step;
                    Pstartpulse = trough_l;
                    Pfrontpulse = trough_l + on_t0_step;
                    continue;
                end
                acf = autocorr(aRFF.y(aRFF.trough_array(end-4):aRFF.trough_array(end)),max_acf_range);
                maxacf = max(acf(floor(on_t0_step*0.5):max_acf_range));
                if (maxacf > 0.7) & ((diff_prob(Tstartpulse) < diff_prob(Tfrontpulse)) | (sum(trough_wss_all < 0.5) > 10))
                    trough_nzc_thresh  = (1+onshiftthresh)*threshfind(trough_nzc_all);
                    trough_ptp_thresh  = (1-onshiftthresh)*threshfind(trough_ptp_all);
                    trough_wss_thresh  = (1+onshiftthresh)*threshfind(trough_wss_all);
                    peak_nzc_thresh    = (1+onshiftthresh)*threshfind(peak_nzc_all);
                    peak_ptp_thresh    = (1-onshiftthresh)*threshfind(peak_ptp_all);
                    peak_wss_thresh    = (1+onshiftthresh)*threshfind(peak_wss_all);
                    
                    alltroughfeats = [trough_ptp_all',trough_nzc_all',trough_wss_all'];
                    deltrough_nzc  = find(trough_nzc_all>trough_nzc_thresh,1,'last');
                    deltrough_ptp  = find(trough_ptp_all<trough_ptp_thresh,1,'last');
                    deltrough_wss  = find(trough_wss_all>trough_wss_thresh,1,'last');
                    troughfeats    = {deltrough_ptp, deltrough_nzc, deltrough_wss};
                    
                    allpeakfeats = [peak_ptp_all',peak_nzc_all',peak_wss_all'];
                    delpeak_nzc  = find(peak_nzc_all>peak_nzc_thresh,1,'last');
                    delpeak_ptp  = find(peak_ptp_all<peak_ptp_thresh,1,'last');
                    delpeak_wss  = find(peak_wss_all>peak_wss_thresh,1,'last');
                    peakfeats    = {delpeak_ptp, delpeak_nzc, delpeak_wss};
                    
                    for i = 1:2
                        if i == 1
                            delfeats = peakfeats;
                            feats    = allpeakfeats;
                        else
                            delfeats = troughfeats;
                            feats    = alltroughfeats;
                        end
                        
                        for features = 1:3
                            if ~isempty(delfeats{features})
                                    if feats(delfeats{features},features) < on_thresh(category, features)
                                        shift = on_shift(features);
                                    else
                                        shift = 0;
                                    end
                                    delcyc(features) = delfeats{features} + shift;
                            else
                                delcyc(features) = NaN;
                            end
                        end
                        
                        D = delcyc(~isnan(delcyc));
                        deltroughpeakval = round(median(D));
                        if i == 1
                            if deltroughpeakval > numel(aRFF.peak_array)
                                delpeak = numel(aRFF.peak_array);
                            else
                                delpeak = deltroughpeakval;
                                switch category
                                    case 1
                                        delpeak = delpeak - 2;
                                    case {2,5}
                                        delpeak = delpeak - 1;
                                    case 4
                                        delpeak = delpeak + 1;
                                end
                                if delpeak <= 0
                                    delpeak = 1;
                                elseif delpeak > numel(aRFF.peak_array)
                                    delpeak = numel(aRFF.peak_array);
                                end
                            end
                            if max(D) > numel(aRFF.peak_array)
                                delpeakmax = numel(aRFF.peak_array);
                            else
                                delpeakmax = max(D);
                            end
                        else
                            if deltroughpeakval > numel(aRFF.trough_array)
                                deltrough = numel(aRFF.trough_array);
                            else
                                deltrough = deltroughpeakval;
                                switch category
                                    case {1,2}
                                        deltrough = deltrough - 2;
                                    case {4,5}
                                        deltrough = deltrough - 1;
                                end
                                if deltrough <= 0
                                    deltrough = 1;
                                elseif deltrough > numel(aRFF.trough_array)
                                    deltrough = numel(aRFF.trough_array);
                                end
                            end
                            if max(D) > numel(aRFF.trough_array)
                                deltroughmax = numel(aRFF.trough_array);
                            else
                                deltroughmax = max(D);
                            end
                        end
                    end
                    
                    long_enough = (aRFF.trough_array(deltroughmax) - aRFF.trough_array(deltrough) + 1) > max_acf_range;
                    if deltroughmax - deltrough > 3 & long_enough
                        acf = autocorr(aRFF.y(aRFF.trough_array(deltrough):aRFF.trough_array(deltroughmax)),max_acf_range);
                        maxacf = max(acf(floor(on_t0_step*0.5):floor(on_t0_step*1.5)));
                        if maxacf < 0.3
                            deltrough = deltroughmax;
                        end
                    end
                    
                    long_enough = (aRFF.peak_array(delpeakmax) - aRFF.peak_array(delpeak) + 1) > max_acf_range;
                    if delpeakmax - delpeak > 3 & long_enough
                        acf = autocorr(aRFF.y(aRFF.peak_array(delpeak):aRFF.peak_array(delpeakmax)),max_acf_range);
                        maxacf = max(acf(floor(on_t0_step*0.5):floor(on_t0_step*1.5)));
                        if maxacf < 0.3
                            delpeak = delpeakmax;
                        end
                    end
                    
                    if isnan(deltrough) | isnan(delpeak)
                        Tstartpulse = peak_l;
                        Tfrontpulse = peak_l + on_t0_step;
                        Pstartpulse = trough_l;
                        Pfrontpulse = trough_l + on_t0_step;
                        continue;
                    end
                    
                    if min(trough_wss_all) > 0.5
                        deltrough = length(trough_wss_all);
                    end
                    if min(peak_wss_all) > 0.5
                        delpeak = length(peak_wss_all);
                    end
                    
                    troughtemp = aRFF.trough_array;
                    peaktemp = aRFF.peak_array;
                    troughtemp(1:deltrough) = [];
                    peaktemp(1:delpeak) = [];
                    
                    on_t0_step = round(1/aRFF.F0c(Tfrontpulse)*aRFF.fs);
                    if on_t0_step > (1/min_pitch_set)*aRFF.fs || on_t0_step < (1/max_pitch_set)*aRFF.fs
                        [on_t0_step,aRFF] = finer_t0_est(Tfrontpulse,aRFF,on_t0_step);
                        if on_t0_step > (1/min_pitch_set)*aRFF.fs || on_t0_step < (1/max_pitch_set)*aRFF.fs
                            on_t0_step = round(1/aRFF.onpitch(aRFF.instancei)*aRFF.fs);
                        end
                    end
                    
                    if (length(troughtemp) > 4) & (length(peaktemp) > 4)
                        aRFF.trough_array(1:deltrough) = [];
                        aRFF.peak_array(1:delpeak) = [];
                        donewithdeletion = 1;
                    end
                end
            end
            
            if length(aRFF.trough_array)>10 & donewithdeletion
                aRFF.troughcyclefull = 1;
            end
            
            if length(aRFF.peak_array)>10 & donewithdeletion
                aRFF.peakcyclefull = 1;
            end
            
            if aRFF.peakcyclefull & aRFF.troughcyclefull
                aRFF = checking_cycles(aRFF,on_t0_step);
                if isempty(aRFF.trough_array)
                    break;
                end
                if length(aRFF.trough_array) < 11 & length(aRFF.peak_array) < 11
                    break;
                end
                aRFF = calcRFF(aRFF);
                if figplot
                    plot_pulses(aRFF);
                    
                    subplot(4,1,4); hold on;
                    if isfield(aRFF,'trough_RFF_Hz')
                        if ~isnan(aRFF.trough_RFF_Hz)
                            plot(14:23, aRFF.trough_RFF(1:10),'.-')
                        else
                            plot(14:23, aRFF.peak_RFF(1:10),'.-')
                        end
                        xlim([1 24])
                    end
                    h = figure(1);
                    
%                     saveas(h,[folname num2str(instancei) '_' aRFF.onoff '.jpg'])
                end
                aRFF.PulseFindingDone = 1;
            end
            
            Tstartpulse = peak_l;
            Tfrontpulse = peak_l + on_t0_step;
            Pstartpulse = trough_l;
            Pfrontpulse = trough_l + on_t0_step;
        end
        save(instancefile,'aRFF')
        
        if isfield(aRFF,'trough_RFF_Hz')
            delfields = {'trough_RFF_Hz','peak_RFF_Hz','trough_RFF','peak_RFF','trough_RFF_meanf0','peak_RFF_meanf0'};
            aRFF = rmfield(aRFF,delfields);
        end
    else
        save(instancefile,'aRFF')
    end
end

