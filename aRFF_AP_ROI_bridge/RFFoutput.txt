function [] = RFFoutput(allfiles)

global min_pitch_set;
global max_pitch_set;
global maxpkn;
global perform_fol;
global stimulicomb;

%save RFF to here.
autofile = [perform_fol 'aRFF.xlsx'];

%Do not change these variables.
numoffcycles = 10;
numoncycles = 10;
aRFF_raw_all = [];
off_rejectcode_all = [];
on_rejectcode_all = [];

for filei = 1:length(allfiles)
    off_rejectcode = zeros(1,maxpkn);
    on_rejectcode = zeros(1,maxpkn);
    off_RFF = zeros(maxpkn,10);
    on_RFF = zeros(maxpkn,10);
    off_RFF_Hz = zeros(maxpkn,1);
    on_RFF_Hz = zeros(maxpkn,1);
    filename = allfiles(filei).name;
    subject = filename(1:end-4);
    sheet = subject;
    
    folname = [perform_fol subject '\var\'];
    stimulifile = [folname 'fric_param.mat'];
    if ~exist(stimulifile)
        continue;
    end
    load(stimulifile)
    min_period_samp = floor(aRFF.fs/max_pitch_set);
    max_period_samp = floor(aRFF.fs/min_pitch_set);
    
    for inst = 1:totalinst
        filename = [folname num2str(inst) '_off.mat'];
        if exist(filename)
            load(filename)
            if isfield(aRFF,'trough_RFF_meanf0') & ~(any(isnan(aRFF.peak_RFF_meanf0)) & any(isnan(aRFF.trough_RFF_meanf0)))
                nanpeakvector = any(isnan(aRFF.peak_RFF_meanf0));
                nantroughvector = any(isnan(aRFF.trough_RFF_meanf0));
                if  nanpeakvector | (~nantroughvector & (aRFF.trough_array(end) > aRFF.peak_array(end)))
                    aRFF_array = aRFF.trough_array;
                    aRFF_Hz = aRFF.trough_RFF_Hz;
                    off_RFF_amp = aRFF.f0y(aRFF_array(end-numoffcycles+1:end));
                    off_RFF_amp_diff = diff(off_RFF_amp);
                    ampthresh = -sum(off_RFF_amp_diff(off_RFF_amp_diff<0))/range(off_RFF_amp);
                else
                    aRFF_array = aRFF.peak_array;
                    aRFF_Hz = aRFF.peak_RFF_Hz;
                    off_RFF_amp = aRFF.f0y(aRFF_array(end-numoffcycles+1:end));
                    off_RFF_amp_diff = diff(off_RFF_amp);
                    ampthresh = sum(off_RFF_amp_diff(off_RFF_amp_diff>0))/range(off_RFF_amp);
                end
                
                if aRFF_array(end)-aRFF_array(1) < max_period_samp
                    max_period_samp = aRFF_array(end)-aRFF_array(1);
                end
                acf = autocorr(aRFF.y(aRFF_array(1):aRFF_array(end)),max_period_samp);
                
                meanF0 = mean(aRFF_Hz(end-numoffcycles+1:end));
                [maxval,maxauto] = max(acf(min_period_samp:max_period_samp));
                dompitch = aRFF.fs/(maxauto + min_period_samp);
                glottalized = (dompitch > 2^(6/12)*meanF0) | (dompitch < 2^(-6/12)*meanF0);
                if (~glottalized & maxauto > 0.8)
                    off_RFF(inst,:) = 12*log2(aRFF_Hz(end-numoffcycles+1:end)./aRFF_Hz(end-numoffcycles+1));
                    off_RFF_Hz(inst) = meanF0;
                elseif glottalized
                    off_rejectcode(inst) = 3;
                else
                    off_rejectcode(inst) = 4;
                end
            else
                off_rejectcode(inst) = 1;
            end
        else
            off_rejectcode(inst) = 1;
        end
        filename = [folname num2str(inst) '_on.mat'];
        if exist(filename)
            load(filename)
            if isfield(aRFF,'trough_RFF_meanf0') & ~(any(isnan(aRFF.peak_RFF_meanf0)) & any(isnan(aRFF.trough_RFF_meanf0)))
                nanpeakvector = any(isnan(aRFF.peak_RFF_meanf0));
                nantroughvector = any(isnan(aRFF.trough_RFF_meanf0));
                if nanpeakvector | (~ nantroughvector & (aRFF.trough_array(1) < aRFF.peak_array(1)))
                    aRFF_array = aRFF.trough_array;
                    aRFF_Hz = aRFF.trough_RFF_Hz;
                    on_RFF_amp = aRFF.f0y(aRFF_array(1:numoncycles));
                    on_RFF_amp_diff = diff(on_RFF_amp);
                    ampthresh = sum(on_RFF_amp_diff(on_RFF_amp_diff>0))/range(on_RFF_amp);
                else
                    aRFF_array = aRFF.peak_array;
                    aRFF_Hz = aRFF.peak_RFF_Hz;
                    on_RFF_amp = aRFF.f0y(aRFF_array(1:numoncycles));
                    on_RFF_amp_diff = diff(on_RFF_amp);
                    ampthresh = -sum(on_RFF_amp_diff(on_RFF_amp_diff<0))/range(on_RFF_amp);
                end
                
                if aRFF_array(end)-aRFF_array(1) < max_period_samp
                    max_period_samp = aRFF_array(end)-aRFF_array(1);
                end
                [acf,lags,bounds] = autocorr(aRFF.y(aRFF_array(1):aRFF_array(end)),max_period_samp);
                meanF0 = mean(aRFF_Hz(1:numoncycles));
                [maxval,maxauto] = max(acf(min_period_samp:max_period_samp));
                dompitch = aRFF.fs/(maxauto + min_period_samp);
                glottalized = (dompitch > 2^(6/12)*meanF0) | (dompitch < 2^(-6/12)*meanF0);
                
                if (~glottalized & maxauto > 0.8)
                    on_RFF(inst,:) = 12*log2(aRFF_Hz(1:numoncycles)./aRFF_Hz(numoncycles));
                    on_RFF_Hz(inst) = meanF0;
                elseif glottalized
                    on_rejectcode(inst) = 3;
                else
                    on_rejectcode(inst) = 4;
                end
            else
                on_rejectcode(inst) = 1;
            end
        else
            on_rejectcode(inst) = 1;
        end
    end
    
    if exist('off_RFF')
        off_RFF_copy = off_RFF;
        %delete zero entries
        potentialRFF = 1:maxpkn;
        potentialRFF(sum(abs(off_RFF'))==0) = [];
        off_RFF_Hz(sum(abs(off_RFF'))==0) = [];
        off_RFF(sum(abs(off_RFF'))==0,:) = [];
        
        %delete wrong pitch instances
        delinst = find(off_RFF_Hz > 2^(6/12)*median(off_RFF_Hz));
        off_rejectcode(potentialRFF(delinst)) = 3;
        off_RFF(delinst,:) = [];
        off_RFF_Hz(delinst) = [];
        potentialRFF(delinst) = [];
        
        %delete sharp transition instances
        acc_off_diff = [0.5 0.5 0.5 0.5 0.8 1.0 1.5 2.5 3.5];
        numinst = size(off_RFF,1);
        delinst2 = find(sum(abs(diff(off_RFF'))' > repmat(acc_off_diff,numinst,1),2)>0);
        off_rejectcode(potentialRFF(delinst2)) = 5;
        off_RFF(delinst2,:) = [];
        off_RFF_Hz(delinst2) = [];
        potentialRFF(delinst2) = [];
        
        for offi = 1:maxpkn
            if ~any(potentialRFF == offi)
                off_RFF_copy(offi,:) = nan(1,10);
            end
        end
        off_RFF = off_RFF_copy;
    else
        off_RFF = nan(maxpkn,10);
    end
    
    if exist('on_RFF')
        on_RFF_copy = on_RFF;
        %delete zero entries
        potentialRFF = 1:maxpkn;
        potentialRFF(sum(abs(on_RFF'))==0) = [];
        on_RFF_Hz(sum(abs(on_RFF'))==0) = [];
        on_RFF(sum(abs(on_RFF'))==0,:) = [];
        
        %delete wrong pitch instances
        delinst = find(on_RFF_Hz' > 2^(6/12)*median(on_RFF_Hz));
        on_rejectcode(potentialRFF(delinst)) = 3;
        on_RFF(delinst,:) = [];
        on_RFF_Hz(delinst) = [];
        potentialRFF(delinst) = [];
        
        %delete sharp transition instances
        acc_on_diff = [6.0 4.0 3.0 2.0 1.0 1.0 1.0 1.0 1.0];
        numinst = size(on_RFF,1);
        delinst2 = find(sum(abs(diff(on_RFF'))' > repmat(acc_on_diff,numinst,1),2)>0);
        on_rejectcode(potentialRFF(delinst2)) = 5;
        on_RFF(delinst2,:) = [];
        on_RFF_Hz(delinst2) = [];
        potentialRFF(delinst2) = [];
        
        for oni = 1:maxpkn
            if ~any(potentialRFF == oni)
                on_RFF_copy(oni,:) = nan(1,10);
            end
        end
        on_RFF = on_RFF_copy;
    else
        on_RFF = nan(maxpkn,10);
    end
    off_RFF = [off_RFF; nan(maxpkn-size(off_RFF,1),10)];
    on_RFF = [on_RFF; nan(maxpkn-size(on_RFF,1),10)];
    
    aRFF_raw = [off_RFF'; nan(4,maxpkn); on_RFF'];
    
    if ~stimulicomb
        excelfirstcol = cell(27,1);
        for exceli = 1:10
            excelfirstcol{exceli+1} = ['OFF' num2str(exceli)];
            excelfirstcol{exceli+15} = ['ON' num2str(exceli)];
        end
        excelfirstcol{26} = ['Off Reject']; 
        excelfirstcol{27} = ['On Reject']; 
        stimlabel = num2cell(1:maxpkn);
        exceloutput = [stimlabel; num2cell(aRFF_raw)];
        exceloutput = [exceloutput; num2cell(off_rejectcode); num2cell(on_rejectcode)];
        exceloutput = [excelfirstcol exceloutput];
        xlswrite(autofile,exceloutput,sheet)
    else        
        aRFF_raw_all = [aRFF_raw_all aRFF_raw];
        off_rejectcode_all = [off_rejectcode_all off_rejectcode];
        on_rejectcode_all = [on_rejectcode_all on_rejectcode];
        
        if mod(filei,3) == 0
            stimlabel = {'afa','ifi','ufu'};
            repmat_stim_label = repmat(stimlabel,[maxpkn 1]);
            stim_label_mult = reshape(repmat_stim_label,1,[]);
            excelfirstcol = cell(27,1);
            for exceli = 1:10
                excelfirstcol{exceli+1} = ['OFF' num2str(exceli)];
                excelfirstcol{exceli+15} = ['ON' num2str(exceli)];
            end
            excelfirstcol{26} = ['Off Reject'];
            excelfirstcol{27} = ['On Reject'];
            exceloutput = [stim_label_mult; num2cell(aRFF_raw_all)];
            exceloutput = [exceloutput; num2cell(off_rejectcode_all); num2cell(on_rejectcode_all)];
            exceloutput = [excelfirstcol exceloutput];
            xlswrite(autofile,exceloutput,sheet(1:end-4));
            aRFF_raw_all = [];
            off_rejectcode_all = [];
            on_rejectcode_all = [];
        end
    end
    clear off_RFF
    clear on_RFF
    clear off_RFF_Hz
    clear on_RFF_Hz
    clear aRFF_raw
end
end
