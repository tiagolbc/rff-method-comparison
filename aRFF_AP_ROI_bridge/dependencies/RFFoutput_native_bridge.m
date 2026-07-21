function [wide_table, long_table, debug_table, landmark_table, cycle_qc_table] = RFFoutput_native_bridge(allfiles, bridge_manifest, out_dir, native_workbook)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% RFFOUTPUT_NATIVE_BRIDGE.M - v16 AP NATIVE-OUTPUT EXPORTER
%
% RFF values and native rejection codes are read from the workbook produced
% by the unmodified original RFFoutput.m.  This function never changes AP
% validity.  It only exports the original results plus observational ROI-QC.
%
% In addition to preserving the original AP output/rejection logic, this
% version exports:
%   * all peak/trough candidates retained by the cycle finder;
%   * the repaired peak/trough traces;
%   * the exact 11 landmarks used to calculate the 10 reported RFF values;
%   * period, boundary-distance, and ROI-side quality-control metrics;
%   * a long table containing only final landmarks from valid measurements.
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

global min_pitch_set;
global max_pitch_set;
global maxpkn;
global perform_fol;

if nargin < 2 || isempty(bridge_manifest)
    bridge_manifest = table();
end
if nargin < 3 || isempty(out_dir)
    out_dir = perform_fol;
end
if nargin < 4 || isempty(native_workbook)
    native_workbook = fullfile(perform_fol,'aRFF.xlsx');
end
if ~exist(native_workbook,'file')
    error('Original aRFF-AP output workbook not found: %s',native_workbook);
end
if ~exist(out_dir, 'dir')
    mkdir(out_dir);
end
if ~istable(bridge_manifest)
    bridge_manifest = readtable(bridge_manifest, 'VariableNamingRule', 'preserve');
end

numoffcycles = 10;
numoncycles  = 10;
wide_rows = {};
long_rows = {};
debug_rows = {};
landmark_rows = {};
cycle_qc_rows = {};

for filei = 1:length(allfiles)
    bridge_filename = allfiles(filei).name;
    subject = bridge_filename(1:end-4);
    folname = fullfile(perform_fol, subject, 'var');
    fricfile = fullfile(folname, 'fric_param.mat');
    if ~exist(fricfile, 'file')
        continue;
    end
    load(fricfile); %#ok<LOAD>
    if exist('roi_metadata', 'var') && istable(roi_metadata)
        meta = roi_metadata;
    else
        meta = bridge_manifest(strcmp(string(bridge_manifest.BridgeFilename), string(bridge_filename)),:);
    end
    total_local = totalinst;
    if isempty(total_local) || total_local < 1
        total_local = height(meta);
    end
    ninst = total_local;
    if maxpkn < ninst
        maxpkn = ninst;
    end

    min_period_samp = floor(aRFF.fs/max_pitch_set);
    max_period_samp_base = floor(aRFF.fs/min_pitch_set);

    off_RFF = nan(ninst,10);
    on_RFF  = nan(ninst,10);
    off_Hz  = nan(ninst,1);
    on_Hz   = nan(ninst,1);
    off_rejectcode = zeros(1,ninst);
    on_rejectcode  = zeros(1,ninst);
    off_chosen = strings(ninst,1);
    on_chosen  = strings(ninst,1);
    off_dbg = cell(ninst,1);
    on_dbg = cell(ninst,1);

    for inst = 1:ninst
        row_meta = meta_row(meta, inst);
        [rff, hz, code, chosen, dbg] = extract_arff_side(folname, inst, 'off', aRFF.fs, min_period_samp, max_period_samp_base, numoffcycles, row_meta);
        if ~isempty(rff)
            off_RFF(inst,:) = rff;
            off_Hz(inst) = hz;
        end
        off_rejectcode(inst) = code;
        off_chosen(inst) = string(chosen);
        off_dbg{inst} = dbg;

        [rff, hz, code, chosen, dbg] = extract_arff_side(folname, inst, 'on', aRFF.fs, min_period_samp, max_period_samp_base, numoncycles, row_meta);
        if ~isempty(rff)
            on_RFF(inst,:) = rff;
            on_Hz(inst) = hz;
        end
        on_rejectcode(inst) = code;
        on_chosen(inst) = string(chosen);
        on_dbg{inst} = dbg;
    end

    % The calculations below are retained only to populate detailed debug
    % structures.  They are not authoritative for result validity.
    % The unmodified original RFFoutput.m workbook replaces all values and
    % rejection codes immediately afterward.
    valid_off = find(all(isfinite(off_RFF),2) & isfinite(off_Hz));
    if ~isempty(valid_off)
        medHz = median(off_Hz(valid_off), 'omitnan');
        del = valid_off(off_Hz(valid_off) > 2^(6/12)*medHz);
        off_rejectcode(del) = 3;
        off_RFF(del,:) = nan;
        off_Hz(del) = nan;
        acc_off_diff = [0.5 0.5 0.5 0.5 0.8 1.0 1.5 2.5 3.5];
        valid_off = find(all(isfinite(off_RFF),2) & isfinite(off_Hz));
        if ~isempty(valid_off)
            del2 = valid_off(sum(abs(diff(off_RFF(valid_off,:),1,2)) > repmat(acc_off_diff,numel(valid_off),1),2)>0);
            off_rejectcode(del2) = 5;
            off_RFF(del2,:) = nan;
            off_Hz(del2) = nan;
        end
    end

    valid_on = find(all(isfinite(on_RFF),2) & isfinite(on_Hz));
    if ~isempty(valid_on)
        medHz = median(on_Hz(valid_on), 'omitnan');
        del = valid_on(on_Hz(valid_on) > 2^(6/12)*medHz);
        on_rejectcode(del) = 3;
        on_RFF(del,:) = nan;
        on_Hz(del) = nan;
        acc_on_diff = [6.0 4.0 3.0 2.0 1.0 1.0 1.0 1.0 1.0];
        valid_on = find(all(isfinite(on_RFF),2) & isfinite(on_Hz));
        if ~isempty(valid_on)
            del2 = valid_on(sum(abs(diff(on_RFF(valid_on,:),1,2)) > repmat(acc_on_diff,numel(valid_on),1),2)>0);
            on_rejectcode(del2) = 5;
            on_RFF(del2,:) = nan;
            on_Hz(del2) = nan;
        end
    end

    [native_off,native_on,native_off_code,native_on_code] = read_native_sheet(native_workbook,subject,ninst);
    off_RFF = native_off;
    on_RFF = native_on;
    off_rejectcode = native_off_code;
    on_rejectcode = native_on_code;

    for inst = 1:ninst
        row_meta = meta_row(meta, inst);
        off_dbg{inst}.rff_st = off_RFF(inst,:);
        on_dbg{inst}.rff_st = on_RFF(inst,:);
        off_dbg{inst} = finalize_debug(off_dbg{inst}, off_rejectcode(inst), all(isfinite(off_RFF(inst,:))));
        on_dbg{inst}  = finalize_debug(on_dbg{inst},  on_rejectcode(inst),  all(isfinite(on_RFF(inst,:))));

        wide_rows(end+1,:) = make_wide_row(row_meta, bridge_filename, subject, inst, off_RFF(inst,:), on_RFF(inst,:), off_Hz(inst), on_Hz(inst), off_rejectcode(inst), on_rejectcode(inst), off_chosen(inst), on_chosen(inst), off_dbg{inst}, on_dbg{inst}); %#ok<AGROW>
        for c = 1:10
            long_rows(end+1,:) = make_long_row(row_meta, bridge_filename, subject, inst, 'OFF', c, off_RFF(inst,c), off_rejectcode(inst)); %#ok<AGROW>
            long_rows(end+1,:) = make_long_row(row_meta, bridge_filename, subject, inst, 'ON', c, on_RFF(inst,c), on_rejectcode(inst)); %#ok<AGROW>
        end
        debug_rows(end+1,:) = make_debug_row(bridge_filename, subject, inst, 'OFF', off_rejectcode(inst), off_chosen(inst), off_dbg{inst}); %#ok<AGROW>
        debug_rows(end+1,:) = make_debug_row(bridge_filename, subject, inst, 'ON', on_rejectcode(inst), on_chosen(inst), on_dbg{inst}); %#ok<AGROW>
        cycle_qc_rows(end+1,:) = make_qc_row(row_meta, bridge_filename, subject, inst, 'OFF', off_rejectcode(inst), off_dbg{inst}); %#ok<AGROW>
        cycle_qc_rows(end+1,:) = make_qc_row(row_meta, bridge_filename, subject, inst, 'ON', on_rejectcode(inst), on_dbg{inst}); %#ok<AGROW>
        if off_rejectcode(inst) == 0
            new_landmarks = make_landmark_rows(row_meta, bridge_filename, subject, inst, 'OFF', off_dbg{inst});
            if isempty(landmark_rows)
                landmark_rows = new_landmarks;
            elseif ~isempty(new_landmarks)
                landmark_rows = [landmark_rows; new_landmarks]; %#ok<AGROW>
            end
        end
        if on_rejectcode(inst) == 0
            new_landmarks = make_landmark_rows(row_meta, bridge_filename, subject, inst, 'ON', on_dbg{inst});
            if isempty(landmark_rows)
                landmark_rows = new_landmarks;
            elseif ~isempty(new_landmarks)
                landmark_rows = [landmark_rows; new_landmarks]; %#ok<AGROW>
            end
        end
    end
end

base_header = {'BridgeFilename','BridgeSubject','Instance','OriginalFilepath','OriginalFilename','Subject','Token','Rep','FricStart','FricEnd','FricLoc'};
rff_header = [arrayfun(@(x) sprintf('OFF%d',x),1:10,'UniformOutput',false), arrayfun(@(x) sprintf('ON%d',x),1:10,'UniformOutput',false)];
status_header = {'OFF_Hz','ON_Hz','OffValid','OnValid','OffRejectCode','OnRejectCode','OffRejectLabel','OnRejectLabel','OffChosenTrace','OnChosenTrace', ...
    'NOffCandidates','NOnCandidates','NOffTraceLandmarks','NOnTraceLandmarks','NOffSelectedLandmarks','NOnSelectedLandmarks','NOffFinalLandmarks','NOnFinalLandmarks', ...
    'OffEdgeGap_ms','OnEdgeGap_ms','OffPeriodCV','OnPeriodCV','OffSkippedBoundaryCandidates','OnSkippedBoundaryCandidates', ...
    'OffBoundaryAdjustmentReason','OnBoundaryAdjustmentReason','OffManualReview','OnManualReview'};
off_sample_header = arrayfun(@(x) sprintf('OFF_sample_%02d',x),1:11,'UniformOutput',false);
on_sample_header = arrayfun(@(x) sprintf('ON_sample_%02d',x),1:11,'UniformOutput',false);
off_time_header = arrayfun(@(x) sprintf('OFF_landmark_%02d_s',x),1:11,'UniformOutput',false);
on_time_header = arrayfun(@(x) sprintf('ON_landmark_%02d_s',x),1:11,'UniformOutput',false);
wide_header = [base_header, rff_header, status_header, off_sample_header, on_sample_header, off_time_header, on_time_header];
long_header = {'BridgeFilename','BridgeSubject','OriginalFilepath','OriginalFilename','Subject','Token','Rep','FricStart','FricEnd','Side','Cycle','RFF_ST','ValidSide','RejectCode','RejectLabel'};
debug_header = {'BridgeFilename','BridgeSubject','Instance','Side','RejectCode','RejectLabel','ChosenTrace','NCandidates','NTraceLandmarks','NSelectedLandmarks','EdgeGap_ms','PeriodCV','WrongSideCount','SkippedBoundaryCandidates','BoundaryAdjustmentReason','MaxPeriodToMedianRatio','MaxAdjacentPeriodRatio','ManualReview','ReviewReason','DebugSummary'};
landmark_header = {'BridgeFilename','BridgeSubject','OriginalFilepath','OriginalFilename','Subject','Token','Rep','Side','LandmarkIndex','LandmarkLabel','SampleIndex','Time_s','ChosenTrace','ValidSide','RejectCode','RejectLabel'};
qc_header = {'BridgeFilename','BridgeSubject','OriginalFilepath','OriginalFilename','Subject','Token','Rep','Side','ValidSide','RejectCode','RejectLabel','ChosenTrace','NCandidates','NTraceLandmarks','NSelectedLandmarks','NFinalLandmarks','EdgeTime_s','EdgeGap_s','EdgeGap_ms','EdgeGapCycles','WrongSideCount','SkippedBoundaryCandidates','BoundaryAdjustmentReason','MedianPeriod_s','PeriodCV','MaxPeriodToMedianRatio','MaxAdjacentPeriodRatio','Contiguous','ManualReview','ReviewReason'};

if isempty(wide_rows)
    wide_table = cell2table(cell(0,numel(wide_header)), 'VariableNames', wide_header);
else
    wide_table = cell2table(wide_rows, 'VariableNames', wide_header);
end
if isempty(long_rows)
    long_table = cell2table(cell(0,numel(long_header)), 'VariableNames', long_header);
else
    long_table = cell2table(long_rows, 'VariableNames', long_header);
end
if isempty(debug_rows)
    debug_table = cell2table(cell(0,numel(debug_header)), 'VariableNames', debug_header);
else
    debug_table = cell2table(debug_rows, 'VariableNames', debug_header);
end
if isempty(landmark_rows)
    landmark_table = cell2table(cell(0,numel(landmark_header)), 'VariableNames', landmark_header);
else
    landmark_table = cell2table(landmark_rows, 'VariableNames', landmark_header);
end
if isempty(cycle_qc_rows)
    cycle_qc_table = cell2table(cell(0,numel(qc_header)), 'VariableNames', qc_header);
else
    cycle_qc_table = cell2table(cycle_qc_rows, 'VariableNames', qc_header);
end

writetable(wide_table, fullfile(out_dir, 'rff_arff_ap_roi_results_wide.csv'));
writetable(long_table, fullfile(out_dir, 'rff_arff_ap_roi_cycles_long.csv'));
writetable(debug_table, fullfile(out_dir, 'rff_arff_ap_roi_debug.csv'));
writetable(landmark_table, fullfile(out_dir, 'rff_arff_ap_roi_landmarks_long.csv'));
writetable(cycle_qc_table, fullfile(out_dir, 'rff_arff_ap_roi_cycle_qc.csv'));
try
    xlsx = fullfile(out_dir, 'rff_arff_ap_roi_results.xlsx');
    writetable(wide_table, xlsx, 'Sheet', 'wide_results');
    writetable(long_table, xlsx, 'Sheet', 'long_cycles');
    writetable(debug_table, xlsx, 'Sheet', 'debug');
    writetable(landmark_table, xlsx, 'Sheet', 'final_landmarks');
    writetable(cycle_qc_table, xlsx, 'Sheet', 'cycle_qc');
catch
    % XLSX export is optional; CSV outputs are primary.
end
end

function [off,on,offcode,oncode] = read_native_sheet(workbook,sheet,ninst)
% Read the exact cell layout written by the original RFFoutput.m:
% OFF1..10 rows 2:11, ON1..10 rows 16:25, reject rows 26:27.
raw = readcell(workbook,'Sheet',sheet);
off = nan(ninst,10);
on = nan(ninst,10);
offcode = zeros(1,ninst);
oncode = zeros(1,ninst);
for inst = 1:ninst
    col = inst+1;
    for cyc = 1:10
        off(inst,cyc) = native_number(raw,cyc+1,col,nan);
        on(inst,cyc) = native_number(raw,cyc+15,col,nan);
    end
    offcode(inst) = native_number(raw,26,col,0);
    oncode(inst) = native_number(raw,27,col,0);
end
offcode = round(offcode);
oncode = round(oncode);
end

function value = native_number(raw,row,col,default)
value = default;
if row > size(raw,1) || col > size(raw,2)
    return;
end
v = raw{row,col};
if isnumeric(v) && isscalar(v) && isfinite(v)
    value = double(v);
elseif islogical(v) && isscalar(v)
    value = double(v);
elseif ischar(v) || isstring(v)
    x = str2double(string(v));
    if isfinite(x)
        value = double(x);
    end
end
end

function [rff, meanF0, rejectcode, chosen, dbg] = extract_arff_side(folname, inst, side, fs, min_period_samp, max_period_samp_base, numcycles, meta)
rff = [];
meanF0 = nan;
rejectcode = 0;
chosen = '';
dbg = empty_debug(side, meta);
matfile = fullfile(folname, sprintf('%d_%s.mat', inst, side));
if ~exist(matfile, 'file')
    rejectcode = 1;
    dbg.reason = 'missing side mat file';
    return;
end
load(matfile); %#ok<LOAD>
if ~exist('aRFF','var') || ~isfield(aRFF,'trough_RFF_meanf0') || ~isfield(aRFF,'peak_RFF_meanf0')
    rejectcode = 1;
    dbg.reason = 'too few periodic cycles';
    return;
end
if any(isnan(aRFF.peak_RFF_meanf0)) && any(isnan(aRFF.trough_RFF_meanf0))
    rejectcode = 1;
    dbg.reason = 'peak and trough traces contain NaN';
    return;
end

peak_candidates = field_or(aRFF,'peak_candidates',field_or(aRFF,'peak_array',[]));
trough_candidates = field_or(aRFF,'trough_candidates',field_or(aRFF,'trough_array',[]));
dbg.candidate_peak_samples = double(peak_candidates(:)');
dbg.candidate_trough_samples = double(trough_candidates(:)');
dbg.candidate_peak_times_s = samples_to_time(dbg.candidate_peak_samples, fs);
dbg.candidate_trough_times_s = samples_to_time(dbg.candidate_trough_samples, fs);
dbg.repaired_peak_samples = double(field_or(aRFF,'peak_array',[]));
dbg.repaired_trough_samples = double(field_or(aRFF,'trough_array',[]));
dbg.repaired_peak_times_s = samples_to_time(dbg.repaired_peak_samples, fs);
dbg.repaired_trough_times_s = samples_to_time(dbg.repaired_trough_samples, fs);

nanpeakvector = any(isnan(aRFF.peak_RFF_meanf0));
nantroughvector = any(isnan(aRFF.trough_RFF_meanf0));
if strcmpi(side,'off')
    if nanpeakvector || (~nantroughvector && (aRFF.trough_array(end) > aRFF.peak_array(end)))
        trace_array = aRFF.trough_array;
        trace_candidates = trough_candidates;
        trace_Hz = aRFF.trough_RFF_Hz;
        chosen = 'trough';
    else
        trace_array = aRFF.peak_array;
        trace_candidates = peak_candidates;
        trace_Hz = aRFF.peak_RFF_Hz;
        chosen = 'peak';
    end
    if numel(trace_array) < numcycles+1 || numel(trace_Hz) < numcycles
        rejectcode = 1;
        dbg.reason = 'too few selected cycles';
        return;
    end
    idx = (numel(trace_Hz)-numcycles+1):numel(trace_Hz);
    selected_samples = trace_array(end-numcycles:end);
    R = 12*log2(trace_Hz(idx)./trace_Hz(idx(1)));
else
    if nanpeakvector || (~nantroughvector && (aRFF.trough_array(1) < aRFF.peak_array(1)))
        trace_array = aRFF.trough_array;
        trace_candidates = trough_candidates;
        trace_Hz = aRFF.trough_RFF_Hz;
        chosen = 'trough';
    else
        trace_array = aRFF.peak_array;
        trace_candidates = peak_candidates;
        trace_Hz = aRFF.peak_RFF_Hz;
        chosen = 'peak';
    end
    if numel(trace_array) < numcycles+1 || numel(trace_Hz) < numcycles
        rejectcode = 1;
        dbg.reason = 'too few selected cycles';
        return;
    end
    idx = 1:numcycles;
    selected_samples = trace_array(1:numcycles+1);
    R = 12*log2(trace_Hz(idx)./trace_Hz(numcycles));
end

selected_samples = double(selected_samples(:)');
selected_times = samples_to_time(selected_samples, fs);
period_samples = abs(diff(selected_samples));
period_s = period_samples ./ fs;
med_period = median(period_s,'omitnan');
period_cv = std(period_s,0,'omitnan') / med_period;
max_period_median_ratio = max(max(period_s./med_period), max(med_period./period_s));
if numel(period_s) >= 2
    max_adjacent_ratio = max(max(period_s(2:end)./period_s(1:end-1)), max(period_s(1:end-1)./period_s(2:end)));
else
    max_adjacent_ratio = 1;
end
edge_time = dbg.edge_time_s;
if strcmpi(side,'off')
    wrong = sum(selected_times >= edge_time);
    edge_gap = edge_time - max(selected_times);
else
    wrong = sum(selected_times <= edge_time);
    edge_gap = min(selected_times) - edge_time;
end
edge_cycles = edge_gap / med_period;
skipped_boundary = boundary_skip_count(trace_candidates, selected_samples, side, edge_time);
boundary_adjustment_reason = '';
if skipped_boundary > 0
    boundary_adjustment_reason = 'candidate_removed_or_repaired';
end
contiguous = numel(selected_samples)==numcycles+1 && all(period_samples>0) && isfinite(max_adjacent_ratio) && max_adjacent_ratio<=2.5;

dbg.chosen = chosen;
dbg.trace_landmarks_samples = double(trace_array(:)');
dbg.trace_landmarks_times_s = samples_to_time(dbg.trace_landmarks_samples, fs);
dbg.final_selected_samples = selected_samples;
dbg.final_selected_times_s = selected_times;
% Backward-compatible names read by the Python v12 plotter.
dbg.selected_samples = selected_samples;
dbg.selected_times_s = selected_times;
dbg.periods_samples = period_samples;
dbg.periods_s = period_s;
dbg.rff_st = R(:)';
dbg.edge_gap_s = edge_gap;
dbg.edge_gap_ms = 1000*edge_gap;
dbg.edge_gap_cycles = edge_cycles;
dbg.wrong_side_count = wrong;
dbg.median_period_s = med_period;
dbg.period_cv = period_cv;
dbg.max_period_to_median_ratio = max_period_median_ratio;
dbg.max_adjacent_period_ratio = max_adjacent_ratio;
dbg.skipped_boundary_candidates = skipped_boundary;
dbg.boundary_adjustment_reason = boundary_adjustment_reason;
dbg.contiguous = contiguous;
dbg.n_candidates = numel(unique([peak_candidates(:); trough_candidates(:)]));
dbg.n_trace_landmarks = numel(trace_array);
dbg.n_selected_landmarks = numel(selected_samples);

% ROI-side, gap, and contiguity findings above are observational QC only.
% They must not alter the original AP rejection code or RFF values.

max_period_samp = max_period_samp_base;
if trace_array(end)-trace_array(1) < max_period_samp
    max_period_samp = abs(trace_array(end)-trace_array(1));
end
if max_period_samp <= min_period_samp || min(trace_array) < 1 || max(trace_array) > numel(aRFF.y)
    rejectcode = 1;
    dbg.reason = 'invalid autocorrelation window';
    return;
end
lo = min(trace_array); hi = max(trace_array);
acf = autocorr(aRFF.y(lo:hi), max_period_samp);
meanF0 = mean(trace_Hz(idx));
search = acf(min_period_samp:max_period_samp);
[maxval,maxauto] = max(search); %#ok<ASGLU>
dompitch = fs/(maxauto + min_period_samp);
glottalized = (dompitch > 2^(6/12)*meanF0) || (dompitch < 2^(-6/12)*meanF0);
if (~glottalized && maxauto > 0.8)
    rff = R(:)';
    rejectcode = 0;
elseif glottalized
    rejectcode = 3;
else
    rejectcode = 4;
end
dbg.meanF0 = meanF0;
dbg.dompitch = dompitch;
dbg.maxacf = maxval;
dbg.reason = reject_label(rejectcode);
end

function dbg = empty_debug(side, meta)
dbg = struct();
dbg.side = upper(side);
if strcmpi(side,'off')
    dbg.edge_time_s = get_meta(meta,'FricStart',nan);
else
    dbg.edge_time_s = get_meta(meta,'FricEnd',nan);
end
dbg.reason = '';
dbg.chosen = '';
dbg.candidate_peak_samples = [];
dbg.candidate_trough_samples = [];
dbg.candidate_peak_times_s = [];
dbg.candidate_trough_times_s = [];
dbg.repaired_peak_samples = [];
dbg.repaired_trough_samples = [];
dbg.repaired_peak_times_s = [];
dbg.repaired_trough_times_s = [];
dbg.trace_landmarks_samples = [];
dbg.trace_landmarks_times_s = [];
dbg.final_selected_samples = [];
dbg.final_selected_times_s = [];
dbg.selected_samples = [];
dbg.selected_times_s = [];
dbg.periods_samples = [];
dbg.periods_s = [];
dbg.rff_st = [];
dbg.edge_gap_s = nan;
dbg.edge_gap_ms = nan;
dbg.edge_gap_cycles = nan;
dbg.wrong_side_count = 0;
dbg.median_period_s = nan;
dbg.period_cv = nan;
dbg.max_period_to_median_ratio = nan;
dbg.max_adjacent_period_ratio = nan;
dbg.skipped_boundary_candidates = 0;
dbg.boundary_adjustment_reason = '';
dbg.contiguous = false;
dbg.n_candidates = 0;
dbg.n_trace_landmarks = 0;
dbg.n_selected_landmarks = 0;
dbg.meanF0 = nan;
dbg.dompitch = nan;
dbg.maxacf = nan;
dbg.reject_code = 1;
dbg.reject_label = reject_label(1);
dbg.valid_side = false;
dbg.manual_review = false;
dbg.review_reason = '';
end

function dbg = finalize_debug(dbg, code, valid)
dbg.reject_code = code;
dbg.reject_label = reject_label(code);
dbg.valid_side = logical(valid && code==0);
reasons = {};
if dbg.valid_side && dbg.n_selected_landmarks ~= 11; reasons{end+1} = 'valid_without_11_final_landmarks'; end %#ok<AGROW>
if dbg.wrong_side_count > 0; reasons{end+1} = 'wrong_side_of_roi'; end %#ok<AGROW>
if dbg.valid_side && dbg.skipped_boundary_candidates > 0; reasons{end+1} = sprintf('skipped_boundary_candidates=%d',dbg.skipped_boundary_candidates); end %#ok<AGROW>
if isfinite(dbg.edge_gap_s) && dbg.edge_gap_s > 0.10; reasons{end+1} = 'edge_gap_over_100_ms'; end %#ok<AGROW>
if isfinite(dbg.period_cv) && dbg.period_cv > 0.25; reasons{end+1} = 'period_cv_over_0.25'; end %#ok<AGROW>
if isfinite(dbg.max_adjacent_period_ratio) && dbg.max_adjacent_period_ratio > 1.80; reasons{end+1} = 'adjacent_period_ratio_over_1.80'; end %#ok<AGROW>
dbg.manual_review = dbg.valid_side && ~isempty(reasons);
dbg.review_reason = strjoin(reasons,'; ');
end

function vals = field_or(s, field, default)
if isstruct(s) && isfield(s,field)
    vals = s.(field);
else
    vals = default;
end
end

function t = samples_to_time(samples, fs)
t = (double(samples)-1) ./ double(fs);
end

function skipped = boundary_skip_count(candidates, selected, side, edgeTime)
c = unique(sort(double(candidates(isfinite(candidates)))));
p = unique(sort(double(selected(isfinite(selected)))));
skipped = 0;
if isempty(c) || isempty(p) || ~isfinite(edgeTime)
    return;
end
tolSamples = 0.5;
% Candidates and selected values are MATLAB sample indices; edgeTime is
% converted by the caller's stored seconds only for ROI-side checks. The
% boundary-skip count therefore uses relative ordering inside the selected
% trace and does not require the edge sample itself.
if strcmpi(side,'off')
    skipped = sum(c > p(end)+tolSamples);
else
    skipped = sum(c < p(1)-tolSamples);
end
end

function meta = meta_row(tbl, inst)
if istable(tbl) && height(tbl) >= inst
    meta = tbl(inst,:);
else
    meta = table();
end
end

function val = get_meta(meta, name, default)
val = default;
if istable(meta) && ismember(name, meta.Properties.VariableNames)
    try
        v = meta.(name);
        if iscell(v), v = v{1}; end
        if isstring(v), v = char(v(1)); end
        if isnumeric(v), val = v(1); else, val = v; end
    catch
        val = default;
    end
end
end

function row = make_wide_row(meta, bridge_filename, bridge_subject, inst, off, on, offHz, onHz, offCode, onCode, offChosen, onChosen, offDbg, onDbg)
orig_path = get_meta(meta, 'Filepath', '');
orig_name = get_meta(meta, 'Filename', '');
subject   = get_meta(meta, 'Subject', bridge_subject);
token     = get_meta(meta, 'Token', '');
rep       = get_meta(meta, 'Rep', inst);
fs0       = get_meta(meta, 'FricStart', nan);
fe0       = get_meta(meta, 'FricEnd', nan);
fl0       = get_meta(meta, 'FricLoc', nan);
offValid = all(isfinite(off)) && offCode==0;
onValid = all(isfinite(on)) && onCode==0;
offSamples = nan(1,11); onSamples = nan(1,11); offTimes = nan(1,11); onTimes = nan(1,11);
if offValid && numel(offDbg.final_selected_samples)==11
    offSamples = reshape(offDbg.final_selected_samples,1,11);
    offTimes = reshape(offDbg.final_selected_times_s,1,11);
end
if onValid && numel(onDbg.final_selected_samples)==11
    onSamples = reshape(onDbg.final_selected_samples,1,11);
    onTimes = reshape(onDbg.final_selected_times_s,1,11);
end
status = {offHz, onHz, offValid, onValid, offCode, onCode, reject_label(offCode), reject_label(onCode), char(offChosen), char(onChosen), ...
    offDbg.n_candidates, onDbg.n_candidates, offDbg.n_trace_landmarks, onDbg.n_trace_landmarks, offDbg.n_selected_landmarks, onDbg.n_selected_landmarks, ...
    11*double(offValid), 11*double(onValid), offDbg.edge_gap_ms, onDbg.edge_gap_ms, offDbg.period_cv, onDbg.period_cv, ...
    offDbg.skipped_boundary_candidates, onDbg.skipped_boundary_candidates, offDbg.boundary_adjustment_reason, onDbg.boundary_adjustment_reason, ...
    offDbg.manual_review, onDbg.manual_review};
row = [{bridge_filename, bridge_subject, inst, orig_path, orig_name, subject, token, rep, fs0, fe0, fl0}, num2cell(off), num2cell(on), status, ...
    num2cell(offSamples), num2cell(onSamples), num2cell(offTimes), num2cell(onTimes)];
end

function row = make_long_row(meta, bridge_filename, bridge_subject, inst, side, cycle, value, code)
orig_path = get_meta(meta, 'Filepath', '');
orig_name = get_meta(meta, 'Filename', '');
subject   = get_meta(meta, 'Subject', bridge_subject);
token     = get_meta(meta, 'Token', '');
rep       = get_meta(meta, 'Rep', inst);
fs0       = get_meta(meta, 'FricStart', nan);
fe0       = get_meta(meta, 'FricEnd', nan);
row = {bridge_filename, bridge_subject, orig_path, orig_name, subject, token, rep, fs0, fe0, side, cycle, value, isfinite(value) && code==0, code, reject_label(code)};
end

function row = make_debug_row(bridge_filename, bridge_subject, inst, side, code, chosen, dbg)
try
    dbgstr = jsonencode(dbg);
catch
    dbgstr = evalc('disp(dbg)');
end
row = {bridge_filename, bridge_subject, inst, side, code, reject_label(code), char(chosen), dbg.n_candidates, dbg.n_trace_landmarks, dbg.n_selected_landmarks, dbg.edge_gap_ms, dbg.period_cv, dbg.wrong_side_count, dbg.skipped_boundary_candidates, dbg.boundary_adjustment_reason, dbg.max_period_to_median_ratio, dbg.max_adjacent_period_ratio, dbg.manual_review, dbg.review_reason, dbgstr};
end

function rows = make_landmark_rows(meta, bridge_filename, bridge_subject, inst, side, dbg)
rows = {};
if ~dbg.valid_side || numel(dbg.final_selected_samples) ~= 11
    return;
end
orig_path = get_meta(meta, 'Filepath', '');
orig_name = get_meta(meta, 'Filename', '');
subject   = get_meta(meta, 'Subject', bridge_subject);
token     = get_meta(meta, 'Token', '');
rep       = get_meta(meta, 'Rep', inst);
for k = 1:11
    rows(end+1,:) = {bridge_filename, bridge_subject, orig_path, orig_name, subject, token, rep, side, k, sprintf('%s_L%02d',side,k), ...
        dbg.final_selected_samples(k), dbg.final_selected_times_s(k), dbg.chosen, true, 0, reject_label(0)}; %#ok<AGROW>
end
end

function row = make_qc_row(meta, bridge_filename, bridge_subject, inst, side, code, dbg)
orig_path = get_meta(meta, 'Filepath', '');
orig_name = get_meta(meta, 'Filename', '');
subject   = get_meta(meta, 'Subject', bridge_subject);
token     = get_meta(meta, 'Token', '');
rep       = get_meta(meta, 'Rep', inst);
row = {bridge_filename, bridge_subject, orig_path, orig_name, subject, token, rep, side, code==0, code, reject_label(code), dbg.chosen, ...
    dbg.n_candidates, dbg.n_trace_landmarks, dbg.n_selected_landmarks, 11*double(code==0), dbg.edge_time_s, dbg.edge_gap_s, dbg.edge_gap_ms, dbg.edge_gap_cycles, ...
    dbg.wrong_side_count, dbg.skipped_boundary_candidates, dbg.boundary_adjustment_reason, dbg.median_period_s, dbg.period_cv, ...
    dbg.max_period_to_median_ratio, dbg.max_adjacent_period_ratio, dbg.contiguous, dbg.manual_review, dbg.review_reason};
end

function label = reject_label(code)
switch code
    case 0
        label = 'not rejected';
    case 1
        label = 'too few periodic cycles';
    case 2
        label = 'fails to reach steady state or unstable';
    case 3
        label = 'glottalized / wrong pitch';
    case 4
        label = 'aperiodic or irregular';
    case 5
        label = 'sharp transition';
    otherwise
        label = 'unknown';
end
end
