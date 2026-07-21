function outputs = RFF_auto_MB_ROI_bridge(manifestPath, outDir, praatPath, varargin)
% RFF_AUTO_MB_ROI_BRIDGE
% ======================
%
% ROI-controlled wrapper for the Mark Berardi RFF_auto_MB MATLAB method.
% v16 restores the original MATLAB->Praat pulse extraction, 10-ms sliding
% windows, voting thresholds, MB rejection sequence, and RFF equations.
%
% This wrapper keeps the original MB cycle-selection and rejection logic as
% closely as possible while allowing externally defined fricative boundaries
% to be supplied from a Python/AVHI workflow.
%
% Key adaptation
% --------------
% Original RFF_auto_MB expects a single FricLoc value per file. This ROI
% bridge accepts FricStart and FricEnd. Offset RFF is calculated using the
% pre-defined FricStart boundary; onset RFF is calculated using the
% pre-defined FricEnd boundary. This preserves the original MB logic for
% pulse extraction, pulse screening, rejection thresholds, and RFF
% calculation while controlling the fricative region across methods.
%
% Required input manifest columns
% -------------------------------
% At minimum, one of the following audio-path options:
%   Filepath or Path       full path to the audio file
%   OR Filename + AudioDir supplied as name-value argument
%
% Required ROI columns:
%   FricStart             fricative onset in seconds
%   FricEnd               fricative offset in seconds
%
% Optional columns:
%   Subject, Token, Rep, Filename
%
% Usage from MATLAB
% -----------------
% outputs = RFF_auto_MB_ROI_bridge('manifest.csv', 'out_dir', '/path/to/Praat');
%
% Usage from command line / Python
% --------------------------------
% matlab -batch "addpath('path/to/package'); RFF_auto_MB_ROI_bridge('manifest.csv','out','/Applications/Praat.app/Contents/MacOS/Praat');"
%
% Outputs
% -------
%   rff_mb_roi_results_wide.csv/.xlsx
%   rff_mb_roi_cycles_long.csv
%   rff_mb_roi_debug.csv
%   rff_mb_roi_manifest_used.csv
%
% Notes
% -----
% The original MB vocal-fry check requires MATLAB pitch().  v16 deliberately
% fails if pitch() is unavailable instead of substituting another algorithm.
%
% Original code license: MIT License, Copyright (c) 2023 mark-berardi.
% ROI bridge adaptation prepared for Tiago L. B. Cruz's RFF method-comparison
% workflow.

p = inputParser;
p.addRequired('manifestPath', @(x) ischar(x) || isstring(x));
p.addRequired('outDir', @(x) ischar(x) || isstring(x));
p.addRequired('praatPath', @(x) ischar(x) || isstring(x));
p.addParameter('AudioDir', '', @(x) ischar(x) || isstring(x));
p.addParameter('SaveXlsx', true, @(x) islogical(x) || isnumeric(x));
p.addParameter('MethodLabel', 'RFF_MB_ROI_MATLAB', @(x) ischar(x) || isstring(x));
p.parse(manifestPath, outDir, praatPath, varargin{:});

manifestPath = char(p.Results.manifestPath);
outDir = char(p.Results.outDir);
praatPath = char(p.Results.praatPath);
audioDir = char(p.Results.AudioDir);
saveXlsx = logical(p.Results.SaveXlsx);
methodLabel = char(p.Results.MethodLabel);

if ~exist(manifestPath, 'file')
    error('Manifest file not found: %s', manifestPath);
end
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

thisDir = fileparts(mfilename('fullpath'));
addpath(thisDir);
addpath(fullfile(thisDir, 'Dependencies'));

global MB_ROI_PRAAT_PATH;
MB_ROI_PRAAT_PATH = praatPath;

T = readtable(manifestPath, 'VariableNamingRule', 'preserve', 'Delimiter', ',');
if height(T) == 0
    error('Manifest table is empty: %s', manifestPath);
end

% Normalize column access while preserving original names.
cols = T.Properties.VariableNames;
col = @(names) pick_col(cols, names);

cFilepath = col({'Filepath','FilePath','Path','AudioPath','AudioFile'});
cFilename = col({'Filename','FileName','File'});
cSubject  = col({'Subject','Participant','Speaker','ID'});
cToken    = col({'Token','Vowel','Task'});
cRep      = col({'Rep','Repetition','Trial','ROI'});
cStart    = col({'FricStart','FricativeStart','Start','StartTime','xmin','x1'});
cEnd      = col({'FricEnd','FricativeEnd','End','EndTime','xmax','x2'});
cLoc      = col({'FricLoc','FricativeLocation','Location','Center','Centre','Mid'});

if isempty(cStart) || isempty(cEnd)
    if isempty(cLoc)
        error('Manifest must contain FricStart/FricEnd columns, or at least FricLoc.');
    end
end

% RFF_auto_MB was designed for one VCV/fricative per audio file.  The app's
% source WAVs contain multiple repetitions, so each manifest ROI is isolated
% between the mid-gaps to its neighbouring ROIs before the original MB code
% is executed.  This is an input/timebase adapter, not a pulse-selection rule.
[analysisStart,analysisEnd] = compute_mb_analysis_segments(T,cFilepath,cFilename,audioDir,cStart,cEnd,cLoc);
T.MBAnalysisStart = analysisStart;
T.MBAnalysisEnd = analysisEnd;

wideRows = cell(height(T), 1);
longRows = cell(height(T), 1);
debugRows = cell(height(T), 1);
landmarkRows = struct([]);
qcRows = struct([]);

fprintf('RFF_auto_MB_ROI_bridge: processing %d ROI rows...\n', height(T));

for ii = 1:height(T)
    try
        row = T(ii,:);
        filePath = resolve_audio_path(row, cFilepath, cFilename, audioDir);
        if ~exist(filePath, 'file')
            error('Audio file not found: %s', filePath);
        end
        [~, fileStem, fileExt] = fileparts(filePath);
        filename = [fileStem fileExt];
        subject = get_optional_text(row, cSubject, '');
        token = get_optional_text(row, cToken, '');
        rep = get_optional_number(row, cRep, NaN);
        if isempty(subject); subject = fileStem; end

        if ~isempty(cStart) && ~isempty(cEnd)
            fricStart = get_required_number(row, cStart, 'FricStart');
            fricEnd = get_required_number(row, cEnd, 'FricEnd');
        else
            fricLoc = get_required_number(row, cLoc, 'FricLoc');
            fricStart = fricLoc;
            fricEnd = fricLoc;
        end
        if ~(isfinite(fricStart) && isfinite(fricEnd) && fricEnd >= fricStart)
            error('Invalid fricative ROI in row %d: FricStart=%g, FricEnd=%g', ii, fricStart, fricEnd);
        end

        result = process_one_mb_roi(filePath, subject, token, rep, fricStart, fricEnd, ...
            analysisStart(ii), analysisEnd(ii), methodLabel);
        wideRows{ii} = result.wide;
        debugRows{ii} = result.debug;
        longRows{ii} = result.long;
        if ~isempty(result.landmarks)
            if isempty(landmarkRows)
                landmarkRows = result.landmarks(:);
            else
                landmarkRows = [landmarkRows; result.landmarks(:)]; %#ok<AGROW>
            end
        end
        if ~isempty(result.qc)
            if isempty(qcRows)
                qcRows = result.qc(:);
            else
                qcRows = [qcRows; result.qc(:)]; %#ok<AGROW>
            end
        end

        fprintf('  %d/%d: %s | off=%d on=%d\n', ii, height(T), filename, result.wide.OffValid, result.wide.OnValid);
    catch ME
        warning('Row %d failed: %s', ii, ME.message);
        wideRows{ii} = failed_wide_row(T(ii,:), cFilepath, cFilename, cSubject, cToken, cRep, cStart, cEnd, cLoc, methodLabel, ME.message);
        debugRows{ii} = failed_debug_row(T(ii,:), cFilename, cSubject, cToken, cRep, cStart, cEnd, cLoc, methodLabel, ME.message);
        failedQC = failed_qc_rows(T(ii,:), cFilepath, cFilename, cSubject, cToken, cRep, cStart, cEnd, cLoc, methodLabel, ME.message);
        if isempty(qcRows)
            qcRows = failedQC(:);
        else
            qcRows = [qcRows; failedQC(:)]; %#ok<AGROW>
        end
    end
end

wide = struct2table(vertcat(wideRows{:}));
nonemptyLongRows = longRows(~cellfun(@isempty, longRows));
if isempty(nonemptyLongRows)
    long = empty_mb_long_table();
else
    long = struct2table(vertcat(nonemptyLongRows{:}));
end
debug = struct2table(vertcat(debugRows{:}));
if isempty(landmarkRows)
    landmarks = empty_mb_landmark_table();
else
    landmarks = struct2table(landmarkRows);
end
if isempty(qcRows)
    cycleQC = empty_mb_qc_table();
else
    cycleQC = struct2table(qcRows);
end

manifestOut = fullfile(outDir, 'rff_mb_roi_manifest_used.csv');
wideCsv = fullfile(outDir, 'rff_mb_roi_results_wide.csv');
longCsv = fullfile(outDir, 'rff_mb_roi_cycles_long.csv');
debugCsv = fullfile(outDir, 'rff_mb_roi_debug.csv');
configJson = fullfile(outDir, 'rff_mb_roi_config.json');
landmarkCsv = fullfile(outDir, 'rff_mb_roi_landmarks_long.csv');
cycleQCCsv = fullfile(outDir, 'rff_mb_roi_cycle_qc.csv');

writetable(T, manifestOut);
writetable(wide, wideCsv);
writetable(long, longCsv);
writetable(debug, debugCsv);
writetable(landmarks, landmarkCsv);
writetable(cycleQC, cycleQCCsv);

config = struct();
config.Version = 'v16 Native MB + external ROI';
config.MethodLabel = methodLabel;
config.ManifestPath = manifestPath;
config.OutputDirectory = outDir;
config.PraatPath = praatPath;
config.AudioDir = audioDir;
config.UsesFricStartForOffset = true;
config.UsesFricEndForOnset = true;
config.MultiROIInputAdapter = 'one VCV segment per ROI, bounded at mid-gaps between neighbouring ROIs';
config.RFFFormula = '12*log2(f0_cycle/f0_reference)';
config.OffsetReference = 'OFF1';
config.OnsetReference = 'ON10';
config.OriginalMBThresholds = struct('VocalFryHz',100,'VarThreshold',2.9e-6,'OutlierPercentile',65,'OutlierMultiplier',1.5,'SteadyStateAbsST',0.8,'LongPauseSeconds',0.25);
config.PulseSelection = struct('Source','MATLAB calls Praat directly', ...
    'PraatOperation','PointProcess periodic cc 75-500 Hz', ...
    'SlidingWindowSeconds',0.01,'OffsetVoteThreshold',0.5,'OnsetVoteThreshold',0.3, ...
    'Implementation','original get_pulses_slide logic with robust text-file I/O');
config.CycleQC = struct('WrongSideRejected',false,'HardMaximumEdgeGapSeconds',[], ...
    'ExactlyElevenFinalLandmarks',true,'ExportsSkippedBoundaryCandidates',true, ...
    'TrueAdjacentPeriodRatio',true,'PeriodToMedianRatioExportedSeparately',true, ...
    'Policy','observational_only_does_not_change_native_MB_validity');
config.PitchForVocalFry = struct('Method','MATLAB pitch()', ...
    'Fallback','none','AudioToolboxRequired',true);
write_text_file(configJson, jsonencode(config, 'PrettyPrint', true));

xlsxPath = '';
if saveXlsx
    xlsxPath = fullfile(outDir, 'rff_mb_roi_results.xlsx');
    try
        writetable(T, xlsxPath, 'Sheet', 'manifest_used');
        writetable(wide, xlsxPath, 'Sheet', 'wide_results');
        writetable(long, xlsxPath, 'Sheet', 'long_cycles');
        writetable(debug, xlsxPath, 'Sheet', 'debug');
        writetable(landmarks, xlsxPath, 'Sheet', 'final_landmarks');
        writetable(cycleQC, xlsxPath, 'Sheet', 'cycle_qc');
    catch ME
        warning('Could not write XLSX output: %s', ME.message);
        xlsxPath = '';
    end
end

outputs = struct();
outputs.manifest_used = manifestOut;
outputs.wide_csv = wideCsv;
outputs.long_csv = longCsv;
outputs.debug_csv = debugCsv;
outputs.config_json = configJson;
outputs.landmarks_csv = landmarkCsv;
outputs.cycle_qc_csv = cycleQCCsv;
outputs.xlsx = xlsxPath;

disp('RFF_auto_MB_ROI_bridge done.');
disp(outputs);
end

% -------------------------------------------------------------------------
function result = process_one_mb_roi(filePath, subject, token, rep, fricStartGlobal, fricEndGlobal, analysisStart, analysisEnd, methodLabel)
% v16: original MB computation with only the location input split into the
% externally supplied FricStart (OFF) and FricEnd (ON) anchors.
[yFull, Fs] = audioread(filePath);
if size(yFull,2) > 1
    [~, ch] = max(sqrt(mean(yFull.^2, 1)));
    yFull = yFull(:, ch);
end
startSample = max(1,floor(analysisStart*Fs)+1);
endSample = min(size(yFull,1),ceil(analysisEnd*Fs));
analysisStart = (startSample-1)/Fs;
analysisEnd = endSample/Fs;
y = yFull(startSample:endSample,:);
analysisFile = [tempname,'.wav'];
audiowrite(analysisFile,y,Fs);
cleanupAnalysisFile = onCleanup(@() delete_if_exists(analysisFile)); %#ok<NASGU>
fricStart = fricStartGlobal-analysisStart;
fricEnd = fricEndGlobal-analysisStart;
if fricStart < 0 || fricEnd > numel(y)/Fs || fricEnd < fricStart
    error('Invalid local MB ROI after isolation: start=%g end=%g duration=%g.',fricStart,fricEnd,numel(y)/Fs);
end
dur = numel(y) / Fs;

global MB_ROI_LAST_PRAAT_DEBUG;
% The Python pulse cache is intentionally ignored.  The original MB method
% obtains the pulse train through Praat from inside MATLAB.
pulses = get_praat_pulse_mb_native(analysisFile, 0, 0, 0);
praat_dbg = MB_ROI_LAST_PRAAT_DEBUG;
praat_dbg.mode = 'matlab_praat_original_full_file';
praat_dbg.nPulses = numel(pulses);
pulseSource = 'matlab_praat_original_MB';
pulses = pulses(isfinite(pulses));
pulses = unique(sort(pulses(:)));
[f0, f0LocSec, pitchSource] = estimate_fry_pitch_native(y, Fs, dur);
filename = get_filename(filePath);

% Execute the original 10-ms sliding-window/voting helper independently at
% the two externally supplied ROI edges.
if any(pulses < fricStart) && any(pulses > fricStart)
    off_candidates = get_pulses_slide_mb_native(analysisFile, fricStart, pulses, 'off');
else
    off_candidates = zeros(0,1);
end
if any(pulses < fricEnd) && any(pulses > fricEnd)
    on_candidates = get_pulses_slide_mb_native(analysisFile, fricEnd, pulses, 'on');
else
    on_candidates = zeros(0,1);
end
off_pulses = off_candidates;
on_pulses = on_candidates;

off_reject = '';
on_reject = '';
off_reject_flag = false;
on_reject_flag = false;
off_boundary_adjustment = '';
on_boundary_adjustment = '';

if numel(off_pulses) < 11
    off_reject_flag = true;
    off_reject = 'not enough pulses';
end
if numel(on_pulses) < 11
    on_reject_flag = true;
    on_reject = 'not enough pulses';
end

if ~off_reject_flag && ~on_reject_flag
    if on_pulses(1) - off_pulses(end) > 0.25
        off_reject_flag = true;
        off_reject = 'long pause between phonemes';
        on_reject_flag = true;
        on_reject = 'long pause between phonemes';
    end
end

% OFFSET SECTION: original MB thresholds and RFF logic.
procStep = 1;
while procStep < 6 && ~off_reject_flag
    off_T = diff(off_pulses);
    switch procStep
        case 1
            idx0 = max(1, numel(off_pulses)-11);
            off_f0 = f0(f0LocSec < fricStart & f0LocSec > off_pulses(idx0));
            if median(off_f0) < 100
                off_reject_flag = true;
                off_reject = 'vocal fry';
            end
            procStep = 2;
        case 2
            if off_T(end) > prctile(off_T(end-9:end), 65) * 1.5
                off_pulses(end) = [];
                off_boundary_adjustment = 'edge_period_outlier_removed';
                if numel(off_pulses) < 11
                    off_reject_flag = true;
                    off_reject = 'not enough pulses after outlier removal';
                else
                    off_T = diff(off_pulses);
                    if off_T(end) > prctile(off_T(end-9:end), 65) * 1.5
                        off_reject_flag = true;
                        off_reject = 'offset period is an outlier';
                    end
                end
            end
            procStep = 3;
        case 3
            if var(off_T(end-9:end)) > 2.9e-6
                off_reject_flag = true;
                off_reject = 'high variance in periods';
            end
            procStep = 4;
        case 4
            if sum(off_T(end-9:end) > prctile(off_T(end-9:end), 65) * 1.5) > 0
                off_reject_flag = true;
                off_reject = 'other onset periods contain an outlier';
            end
            procStep = 5;
        case 5
            off_F = 1 ./ off_T;
            off_RFF_tmp = 12 .* log2(off_F(end-9:end) ./ off_F(end-9));
            if abs(off_RFF_tmp(2)) > 0.8
                off_reject_flag = true;
                off_reject = 'failure to reach steady-state';
            end
            procStep = 6;
    end
end

% ONSET SECTION: original MB thresholds and RFF logic.
procStep = 1;
while procStep < 6 && ~on_reject_flag
    on_T = diff(on_pulses);
    switch procStep
        case 1
            idx1 = min(11, numel(on_pulses));
            on_f0 = f0(f0LocSec > fricEnd & f0LocSec < on_pulses(idx1));
            if median(on_f0) < 100 && ~on_reject_flag
                on_reject_flag = true;
                on_reject = 'vocal fry';
            end
            procStep = 2;
        case 2
            if on_T(1) > prctile(on_T(1:10), 65) * 1.5
                on_pulses(1) = [];
                on_boundary_adjustment = 'edge_period_outlier_removed';
                if numel(on_pulses) < 11
                    on_reject_flag = true;
                    on_reject = 'not enough pulses after outlier removal';
                else
                    on_T = diff(on_pulses);
                    if on_T(1) > prctile(on_T(1:10), 65) * 1.5
                        on_reject_flag = true;
                        on_reject = 'onset period is an outlier';
                    end
                end
            end
            procStep = 3;
        case 3
            if var(on_T(1:10)) > 2.9e-6
                on_reject_flag = true;
                on_reject = 'high variance in periods';
            end
            procStep = 4;
        case 4
            if sum(on_T(2:10) > prctile(on_T(1:10), 65) * 1.5) > 0
                on_reject_flag = true;
                on_reject = 'other onset periods contain an outlier';
            end
            procStep = 5;
        case 5
            on_F = 1 ./ on_T;
            on_RFF_tmp = 12 .* log2(on_F(1:10) ./ on_F(10));
            if abs(on_RFF_tmp(9)) > 0.8
                on_reject_flag = true;
                on_reject = 'failure to reach steady-state';
            end
            procStep = 6;
    end
end

% Exact attempted windows after all MB pulse-removal steps.
OFF_attempt = nan(1,11);
ON_attempt = nan(1,11);
if numel(off_pulses) >= 11
    OFF_attempt = reshape(off_pulses(end-10:end), 1, 11);
end
if numel(on_pulses) >= 11
    ON_attempt = reshape(on_pulses(1:11), 1, 11);
end

% Boundary distance, wrong-side, and contiguity findings are observational
% QC only in v16.  They never alter the native MB rejection flags.

OFF_pulse = nan(1,11);
ON_pulse = nan(1,11);
OFF_RFF = nan(1,10);
ON_RFF = nan(1,10);

if ~off_reject_flag
    OFF_pulse = OFF_attempt;
    off_T = diff(OFF_pulse);
    off_F = 1 ./ off_T;
    OFF_RFF = 12 .* log2(off_F ./ off_F(1));
else
    if isempty(off_reject); off_reject = 'rejected'; end
end
if ~on_reject_flag
    ON_pulse = ON_attempt;
    on_T = diff(ON_pulse);
    on_F = 1 ./ on_T;
    ON_RFF = 12 .* log2(on_F ./ on_F(10));
else
    if isempty(on_reject); on_reject = 'rejected'; end
end

% Restore the original full-file timebase for all exported landmarks/QC.
off_candidates = off_candidates + analysisStart;
on_candidates = on_candidates + analysisStart;
OFF_attempt = OFF_attempt + analysisStart;
ON_attempt = ON_attempt + analysisStart;
OFF_pulse = OFF_pulse + analysisStart;
ON_pulse = ON_pulse + analysisStart;
fricStart = fricStartGlobal;
fricEnd = fricEndGlobal;

[offQC, offReview] = make_cycle_qc(methodLabel, subject, filename, filePath, token, rep, 'OFF', fricStart, off_candidates, OFF_attempt, OFF_pulse, ~off_reject_flag, off_reject, pulseSource, off_boundary_adjustment);
[onQC, onReview] = make_cycle_qc(methodLabel, subject, filename, filePath, token, rep, 'ON', fricEnd, on_candidates, ON_attempt, ON_pulse, ~on_reject_flag, on_reject, pulseSource, on_boundary_adjustment);

wide = struct();
wide.Method = string(methodLabel);
wide.Subject = string(subject);
wide.Filename = string(filename);
wide.Filepath = string(filePath);
wide.Token = string(token);
wide.Rep = rep;
wide.FricStart = fricStart;
wide.FricEnd = fricEnd;
wide.FricDur = fricEnd - fricStart;
wide.OffValid = ~off_reject_flag;
wide.OnValid = ~on_reject_flag;
wide.OffReject = string(off_reject);
wide.OnReject = string(on_reject);
wide.NOffLandmarks = sum(isfinite(OFF_pulse));
wide.NOnLandmarks = sum(isfinite(ON_pulse));
wide.NOffCandidates = numel(off_candidates);
wide.NOnCandidates = numel(on_candidates);
wide.PulseSource = string(pulseSource);
wide.PitchSource = string(pitchSource);
wide.OffEdgeGap_ms = offQC.EdgeGap_ms;
wide.OnEdgeGap_ms = onQC.EdgeGap_ms;
wide.OffPeriodCV = offQC.PeriodCV;
wide.OnPeriodCV = onQC.PeriodCV;
wide.OffSkippedBoundaryCandidates = offQC.SkippedBoundaryCandidates;
wide.OnSkippedBoundaryCandidates = onQC.SkippedBoundaryCandidates;
wide.OffBoundaryAdjustmentReason = offQC.BoundaryAdjustmentReason;
wide.OnBoundaryAdjustmentReason = onQC.BoundaryAdjustmentReason;
wide.OffManualReview = offReview;
wide.OnManualReview = onReview;
for k = 1:10
    wide.(sprintf('OFF%d', k)) = OFF_RFF(k);
end
for k = 1:10
    wide.(sprintf('ON%d', k)) = ON_RFF(k);
end
wide.OFF10 = OFF_RFF(10);
wide.ON1 = ON_RFF(1);
for k = 1:11
    wide.(sprintf('OFF_pulse_%02d_s', k)) = OFF_pulse(k);
    wide.(sprintf('ON_pulse_%02d_s', k)) = ON_pulse(k);
end

longTemplate = make_cycle_row(methodLabel, subject, filename, filePath, token, rep, fricStart, fricEnd, 'OFF', 1, NaN, false, '');
long = repmat(longTemplate, 20, 1);
rr = 0;
for k = 1:10
    rr = rr + 1;
    long(rr) = make_cycle_row(methodLabel, subject, filename, filePath, token, rep, fricStart, fricEnd, 'OFF', k, OFF_RFF(k), ~off_reject_flag, off_reject);
end
for k = 1:10
    rr = rr + 1;
    long(rr) = make_cycle_row(methodLabel, subject, filename, filePath, token, rep, fricStart, fricEnd, 'ON', k, ON_RFF(k), ~on_reject_flag, on_reject);
end

offLandmarks = make_landmark_rows(methodLabel, subject, filename, filePath, token, rep, 'OFF', OFF_pulse, ~off_reject_flag, off_reject, pulseSource);
onLandmarks = make_landmark_rows(methodLabel, subject, filename, filePath, token, rep, 'ON', ON_pulse, ~on_reject_flag, on_reject, pulseSource);
if isempty(offLandmarks)
    landmarks = onLandmarks;
elseif isempty(onLandmarks)
    landmarks = offLandmarks;
else
    landmarks = [offLandmarks; onLandmarks];
end
qc = [offQC; onQC];

debug = struct();
debug.Method = string(methodLabel);
debug.Subject = string(subject);
debug.Filename = string(filename);
debug.Token = string(token);
debug.Rep = rep;
debug.FricStart = fricStart;
debug.FricEnd = fricEnd;
debug.MBAnalysisStart = analysisStart;
debug.MBAnalysisEnd = analysisEnd;
debug.NGlobalPulses = numel(pulses);
debug.PulseSource = string(pulseSource);
debug.PitchSource = string(pitchSource);
try
    debug.PraatMode = string(praat_dbg.mode);
    debug.PraatExecutable = string(praat_dbg.exe);
    debug.PraatStatus = double(praat_dbg.status);
    debug.PraatOutFileExists = logical(praat_dbg.outFileExists);
    debug.PraatStdout = string(praat_dbg.stdout);
catch
    debug.PraatMode = string('');
    debug.PraatExecutable = string('');
    debug.PraatStatus = NaN;
    debug.PraatOutFileExists = false;
    debug.PraatStdout = string('');
end
debug.NOffCandidates = numel(off_candidates);
debug.NOnCandidates = numel(on_candidates);
debug.NOffPulsesAfterROISelection = numel(off_pulses);
debug.NOnPulsesAfterROISelection = numel(on_pulses);
debug.OffReject = string(off_reject);
debug.OnReject = string(on_reject);
debug.OffCandidatePulsesJSON = string(jsonencode(off_candidates(:)'));
debug.OnCandidatePulsesJSON = string(jsonencode(on_candidates(:)'));
debug.OffAttemptedPulsesJSON = string(jsonencode(OFF_attempt));
debug.OnAttemptedPulsesJSON = string(jsonencode(ON_attempt));
debug.OffFinalPulsesJSON = string(jsonencode(OFF_pulse));
debug.OnFinalPulsesJSON = string(jsonencode(ON_pulse));
debug.OffSkippedBoundaryCandidates = offQC.SkippedBoundaryCandidates;
debug.OnSkippedBoundaryCandidates = onQC.SkippedBoundaryCandidates;
debug.OffBoundaryAdjustmentReason = offQC.BoundaryAdjustmentReason;
debug.OnBoundaryAdjustmentReason = onQC.BoundaryAdjustmentReason;
% Backward-compatible names used by the Python v12 plot reader.
debug.OffSelectedPulsesJSON = debug.OffFinalPulsesJSON;
debug.OnSelectedPulsesJSON = debug.OnFinalPulsesJSON;
debug.OffRFFJSON = string(jsonencode(OFF_RFF));
debug.OnRFFJSON = string(jsonencode(ON_RFF));
debug.OffQCJSON = string(jsonencode(offQC));
debug.OnQCJSON = string(jsonencode(onQC));
debug.Error = string('');

result = struct('wide', wide, 'long', long, 'debug', debug, 'landmarks', landmarks, 'qc', qc);
end

function row = make_cycle_row(methodLabel, subject, filename, filePath, token, rep, fricStart, fricEnd, side, cycle, value, validSide, reject)
row = struct('Method',string(methodLabel),'Subject',string(subject),'Filename',string(filename),'Filepath',string(filePath), ...
    'Token',string(token),'Rep',rep,'FricStart',fricStart,'FricEnd',fricEnd,'Side',string(side), ...
    'Cycle',cycle,'RFF_ST',value,'ValidSide',logical(validSide),'Reject',string(reject));
end

function rows = make_landmark_rows(methodLabel, subject, filename, filePath, token, rep, side, finalPulses, validSide, reject, pulseSource)
rows = struct([]);
if ~validSide || sum(isfinite(finalPulses)) ~= 11
    return;
end
finalPulses = finalPulses(isfinite(finalPulses));
for k = 1:11
    rr = struct();
    rr.Method = string(methodLabel);
    rr.Subject = string(subject);
    rr.Filename = string(filename);
    rr.Filepath = string(filePath);
    rr.Token = string(token);
    rr.Rep = rep;
    rr.Side = string(side);
    rr.LandmarkIndex = k;
    rr.LandmarkLabel = string(sprintf('%s_L%02d', side, k));
    rr.Time_s = finalPulses(k);
    rr.SampleIndex = NaN;
    rr.ChosenTrace = string('Praat pulse');
    rr.PulseSource = string(pulseSource);
    rr.ValidSide = logical(validSide);
    rr.Reject = string(reject);
    rows = [rows; rr]; %#ok<AGROW>
end
end

function [qc, review] = make_cycle_qc(methodLabel, subject, filename, filePath, token, rep, side, edgeTime, candidates, attempted, finalPulses, validSide, reject, pulseSource, boundaryAdjustmentReason)
p = attempted(isfinite(attempted));
p = sort(p(:));
periods = diff(p);
med = median(periods, 'omitnan');
if isempty(periods) || ~isfinite(med) || med <= 0
    periodCV = NaN;
    maxMedianRatio = NaN;
    maxAdjacentRatio = NaN;
else
    periodCV = std(periods,0,'omitnan') / med;
    maxMedianRatio = max(max(periods./med), max(med./periods));
    if numel(periods) >= 2
        maxAdjacentRatio = max(max(periods(2:end)./periods(1:end-1)), max(periods(1:end-1)./periods(2:end)));
    else
        maxAdjacentRatio = 1;
    end
end
if isempty(p)
    gap = NaN;
    wrong = 0;
elseif strcmpi(side,'OFF')
    gap = edgeTime - p(end);
    wrong = sum(p >= edgeTime);
else
    gap = p(1) - edgeTime;
    wrong = sum(p <= edgeTime);
end
skipped = boundary_skip_count(candidates, p, side, edgeTime);
if skipped > 0 && strlength(string(boundaryAdjustmentReason)) == 0
    boundaryAdjustmentReason = 'selected_window_not_edge_adjacent';
end
edgeCycles = gap / med;
contiguous = numel(p)==11 && all(periods>0) && (isnan(maxAdjacentRatio) || maxAdjacentRatio<=2.5);
reasons = {};
if validSide && numel(finalPulses(isfinite(finalPulses))) ~= 11; reasons{end+1} = 'valid_without_11_final_landmarks'; end %#ok<AGROW>
if wrong > 0; reasons{end+1} = 'wrong_side_of_roi'; end %#ok<AGROW>
if validSide && skipped > 0; reasons{end+1} = sprintf('skipped_boundary_candidates=%d', skipped); end %#ok<AGROW>
if isfinite(gap) && gap > 0.10; reasons{end+1} = 'edge_gap_over_100_ms'; end %#ok<AGROW>
if isfinite(periodCV) && periodCV > 0.25; reasons{end+1} = 'period_cv_over_0.25'; end %#ok<AGROW>
if isfinite(maxAdjacentRatio) && maxAdjacentRatio > 1.80; reasons{end+1} = 'adjacent_period_ratio_over_1.80'; end %#ok<AGROW>
review = validSide && ~isempty(reasons);
qc = struct();
qc.Method = string(methodLabel); qc.Subject = string(subject); qc.Filename = string(filename); qc.Filepath = string(filePath);
qc.Token = string(token); qc.Rep = rep; qc.Side = string(side); qc.ValidSide = logical(validSide); qc.Reject = string(reject);
qc.PulseSource = string(pulseSource); qc.NCandidates = numel(candidates); qc.NAttemptedLandmarks = numel(p);
qc.NFinalLandmarks = sum(isfinite(finalPulses)); qc.EdgeTime_s = edgeTime; qc.EdgeGap_s = gap; qc.EdgeGap_ms = 1000*gap;
qc.EdgeGapCycles = edgeCycles; qc.WrongSideCount = wrong; qc.SkippedBoundaryCandidates = skipped;
qc.BoundaryAdjustmentReason = string(boundaryAdjustmentReason); qc.MedianPeriod_s = med; qc.PeriodCV = periodCV;
qc.MaxPeriodToMedianRatio = maxMedianRatio; qc.MaxAdjacentPeriodRatio = maxAdjacentRatio;
qc.Contiguous = logical(contiguous); qc.ManualReview = logical(review);
qc.ReviewReason = string(strjoin(reasons,'; '));
end

function skipped = boundary_skip_count(candidates, selected, side, edgeTime)
c = unique(sort(candidates(isfinite(candidates))));
p = unique(sort(selected(isfinite(selected))));
skipped = 0;
if isempty(c) || isempty(p) || ~isfinite(edgeTime)
    return;
end
tol = 1e-9;
if strcmpi(side,'OFF')
    skipped = sum(c > p(end)+tol & c < edgeTime-tol);
else
    skipped = sum(c < p(1)-tol & c > edgeTime+tol);
end
end

% -------------------------------------------------------------------------
function [segmentStart,segmentEnd] = compute_mb_analysis_segments(T,cFilepath,cFilename,audioDir,cStart,cEnd,cLoc)
n = height(T);
segmentStart = zeros(n,1);
segmentEnd = nan(n,1);
paths = strings(n,1);
starts = nan(n,1);
ends = nan(n,1);
for i = 1:n
    paths(i) = string(resolve_audio_path(T(i,:),cFilepath,cFilename,audioDir));
    if ~isempty(cStart) && ~isempty(cEnd)
        starts(i) = get_required_number(T(i,:),cStart,'FricStart');
        ends(i) = get_required_number(T(i,:),cEnd,'FricEnd');
    else
        starts(i) = get_required_number(T(i,:),cLoc,'FricLoc');
        ends(i) = starts(i);
    end
end
uniquePaths = unique(paths,'stable');
for p = 1:numel(uniquePaths)
    idx = find(paths == uniquePaths(p));
    [~,ord] = sort(starts(idx));
    idx = idx(ord);
    info = audioinfo(char(uniquePaths(p)));
    dur = info.Duration;
    for j = 1:numel(idx)
        ii = idx(j);
        if j == 1
            left = 0;
        else
            prev = idx(j-1);
            left = 0.5*(ends(prev)+starts(ii));
        end
        if j == numel(idx)
            right = dur;
        else
            nxt = idx(j+1);
            right = 0.5*(ends(ii)+starts(nxt));
        end
        segmentStart(ii) = max(0,min(left,starts(ii)));
        segmentEnd(ii) = min(dur,max(right,ends(ii)));
        if segmentEnd(ii) <= segmentStart(ii)
            error('Could not isolate MB ROI row %d inside %s.',ii,char(uniquePaths(p)));
        end
    end
end
end

function name = pick_col(cols, names)
name = '';
keys = lower(regexprep(cols, '[\s_\-]', ''));
for i = 1:numel(names)
    k = lower(regexprep(names{i}, '[\s_\-]', ''));
    idx = find(strcmp(keys, k), 1, 'first');
    if ~isempty(idx)
        name = cols{idx};
        return;
    end
end
end

function txt = get_optional_text(row, colname, default)
if isempty(colname)
    txt = default;
else
    val = row.(colname)(1);
    if iscell(val); val = val{1}; end
    try
        missing = any(ismissing(val));
    catch
        missing = false;
    end
    if missing
        txt = default;
    else
        txt = char(string(val));
        if strcmpi(txt, 'missing') || strcmpi(txt, 'nan')
            txt = default;
        end
    end
end
end

function val = get_optional_number(row, colname, default)
if isempty(colname)
    val = default;
else
    raw = row.(colname)(1);
    if iscell(raw); raw = raw{1}; end
    val = str2double(string(raw));
    if isnan(val)
        try; val = double(raw); catch; val = default; end %#ok<CTCH>
    end
    if ~isfinite(val); val = default; end
end
end

function val = get_required_number(row, colname, label)
raw = row.(colname)(1);
if iscell(raw); raw = raw{1}; end
val = str2double(string(raw));
if isnan(val)
    try; val = double(raw); catch; val = NaN; end %#ok<CTCH>
end
if ~isfinite(val)
    error('Required numeric value %s is missing or invalid.', label);
end
end


function filePath = resolve_audio_path(row, cFilepath, cFilename, audioDir)
filePath = '';
if ~isempty(cFilepath)
    filePath = get_optional_text(row, cFilepath, '');
end
if isempty(filePath) && ~isempty(cFilename)
    fn = get_optional_text(row, cFilename, '');
    if ~isempty(audioDir)
        filePath = fullfile(audioDir, fn);
    else
        filePath = fn;
    end
end
if isempty(filePath)
    error('Could not resolve audio path. Provide Filepath/Path or Filename + AudioDir.');
end
end

function fn = get_filename(filePath)
[~, a, b] = fileparts(filePath);
fn = [a b];
end

function locSec = normalize_pitch_locations(loc, Fs, dur)
locSec = double(loc(:));
if isempty(locSec)
    return;
end
% Current MATLAB pitch() usually returns seconds. Some legacy code assumes
% samples. Convert only when values clearly exceed duration.
if max(locSec, [], 'omitnan') > dur + 1
    locSec = locSec ./ Fs;
end
end

function [f0, locSec, source] = estimate_fry_pitch_native(y, Fs, dur)
% Preserve the original MB dependency on MATLAB pitch().  Location units are
% normalized only for MATLAB-release compatibility; the pitch values and
% the original <100-Hz vocal-fry decision are unchanged.
if isempty(which('pitch'))
    error('The original MB method requires MATLAB pitch() (Audio Toolbox).');
end
[f0, loc] = pitch(y, Fs);
locSec = normalize_pitch_locations(loc, Fs, dur);
good = isfinite(f0) & f0 > 0 & isfinite(locSec);
f0 = double(f0(good));
locSec = double(locSec(good));
if isempty(f0)
    error('MATLAB pitch() returned no usable values for the MB vocal-fry check.');
end
source = 'matlab_pitch_original_MB';
end

function row = failed_wide_row(Trow, cFilepath, cFilename, cSubject, cToken, cRep, cStart, cEnd, cLoc, methodLabel, message)
row = struct();
row.Method = string(methodLabel);
row.Subject = string(get_optional_text(Trow, cSubject, ''));
row.Filename = string(get_optional_text(Trow, cFilename, ''));
row.Filepath = string(get_optional_text(Trow, cFilepath, ''));
row.Token = string(get_optional_text(Trow, cToken, ''));
row.Rep = get_optional_number(Trow, cRep, NaN);
if ~isempty(cStart) && ~isempty(cEnd)
    row.FricStart = get_optional_number(Trow, cStart, NaN);
    row.FricEnd = get_optional_number(Trow, cEnd, NaN);
elseif ~isempty(cLoc)
    loc = get_optional_number(Trow, cLoc, NaN);
    row.FricStart = loc;
    row.FricEnd = loc;
else
    row.FricStart = NaN;
    row.FricEnd = NaN;
end
row.FricDur = row.FricEnd - row.FricStart;
row.OffValid = false;
row.OnValid = false;
row.OffReject = string(['row failed: ' message]);
row.OnReject = string(['row failed: ' message]);
row.NOffLandmarks = 0;
row.NOnLandmarks = 0;
row.NOffCandidates = 0;
row.NOnCandidates = 0;
row.PulseSource = string('row_failed');
row.PitchSource = string('row_failed');
row.OffEdgeGap_ms = NaN;
row.OnEdgeGap_ms = NaN;
row.OffPeriodCV = NaN;
row.OnPeriodCV = NaN;
row.OffSkippedBoundaryCandidates = 0;
row.OnSkippedBoundaryCandidates = 0;
row.OffBoundaryAdjustmentReason = string('');
row.OnBoundaryAdjustmentReason = string('');
row.OffManualReview = false;
row.OnManualReview = false;
for k = 1:10
    row.(sprintf('OFF%d', k)) = NaN;
end
for k = 1:10
    row.(sprintf('ON%d', k)) = NaN;
end
row.OFF10 = NaN;
row.ON1 = NaN;
for k = 1:11
    row.(sprintf('OFF_pulse_%02d_s', k)) = NaN;
    row.(sprintf('ON_pulse_%02d_s', k)) = NaN;
end
end


function dbg = failed_debug_row(Trow, cFilename, cSubject, cToken, cRep, cStart, cEnd, cLoc, methodLabel, message)
dbg = struct();
dbg.Method = string(methodLabel);
dbg.Subject = string(get_optional_text(Trow, cSubject, ''));
dbg.Filename = string(get_optional_text(Trow, cFilename, ''));
dbg.Token = string(get_optional_text(Trow, cToken, ''));
dbg.Rep = get_optional_number(Trow, cRep, NaN);
if ~isempty(cStart) && ~isempty(cEnd)
    dbg.FricStart = get_optional_number(Trow, cStart, NaN);
    dbg.FricEnd = get_optional_number(Trow, cEnd, NaN);
elseif ~isempty(cLoc)
    loc = get_optional_number(Trow, cLoc, NaN);
    dbg.FricStart = loc;
    dbg.FricEnd = loc;
else
    dbg.FricStart = NaN;
    dbg.FricEnd = NaN;
end
dbg.NGlobalPulses = 0;
dbg.PulseSource = string('row_failed');
dbg.PitchSource = string('row_failed');
dbg.PraatMode = string('');
dbg.PraatExecutable = string('');
dbg.PraatStatus = NaN;
dbg.PraatOutFileExists = false;
dbg.PraatStdout = string('');
dbg.NOffCandidates = 0;
dbg.NOnCandidates = 0;
dbg.NOffPulsesAfterROISelection = 0;
dbg.NOnPulsesAfterROISelection = 0;
dbg.OffReject = string(['row failed: ' message]);
dbg.OnReject = string(['row failed: ' message]);
dbg.OffCandidatePulsesJSON = string('[]');
dbg.OnCandidatePulsesJSON = string('[]');
dbg.OffAttemptedPulsesJSON = string('[]');
dbg.OnAttemptedPulsesJSON = string('[]');
dbg.OffFinalPulsesJSON = string('[]');
dbg.OnFinalPulsesJSON = string('[]');
dbg.OffSkippedBoundaryCandidates = 0;
dbg.OnSkippedBoundaryCandidates = 0;
dbg.OffBoundaryAdjustmentReason = string('');
dbg.OnBoundaryAdjustmentReason = string('');
dbg.OffSelectedPulsesJSON = string('[]');
dbg.OnSelectedPulsesJSON = string('[]');
dbg.OffRFFJSON = string('[]');
dbg.OnRFFJSON = string('[]');
dbg.OffQCJSON = string('{}');
dbg.OnQCJSON = string('{}');
dbg.Error = string(message);
end


function rows = failed_qc_rows(Trow, cFilepath, cFilename, cSubject, cToken, cRep, cStart, cEnd, cLoc, methodLabel, message)
subject = get_optional_text(Trow, cSubject, '');
filename = get_optional_text(Trow, cFilename, '');
filepath = get_optional_text(Trow, cFilepath, '');
token = get_optional_text(Trow, cToken, '');
rep = get_optional_number(Trow, cRep, NaN);
if ~isempty(cStart) && ~isempty(cEnd)
    fst = get_optional_number(Trow, cStart, NaN);
    fend = get_optional_number(Trow, cEnd, NaN);
elseif ~isempty(cLoc)
    fst = get_optional_number(Trow, cLoc, NaN);
    fend = fst;
else
    fst = NaN; fend = NaN;
end
base = struct('Method',string(methodLabel),'Subject',string(subject),'Filename',string(filename),'Filepath',string(filepath), ...
    'Token',string(token),'Rep',rep,'Side',string('OFF'),'ValidSide',false,'Reject',string(['row failed: ' message]), ...
    'PulseSource',string('row_failed'),'NCandidates',0,'NAttemptedLandmarks',0,'NFinalLandmarks',0, ...
    'EdgeTime_s',fst,'EdgeGap_s',NaN,'EdgeGap_ms',NaN,'EdgeGapCycles',NaN,'WrongSideCount',0, ...
    'SkippedBoundaryCandidates',0,'BoundaryAdjustmentReason',string(''),'MedianPeriod_s',NaN,'PeriodCV',NaN, ...
    'MaxPeriodToMedianRatio',NaN,'MaxAdjacentPeriodRatio',NaN,'Contiguous',false, ...
    'ManualReview',false,'ReviewReason',string(''));
rows = repmat(base,2,1);
rows(2).Side = string('ON');
rows(2).EdgeTime_s = fend;
end

function T = empty_mb_long_table()
T = table(strings(0,1),strings(0,1),strings(0,1),strings(0,1),strings(0,1),zeros(0,1),zeros(0,1),zeros(0,1),strings(0,1),zeros(0,1),zeros(0,1),false(0,1),strings(0,1), ...
    'VariableNames',{'Method','Subject','Filename','Filepath','Token','Rep','FricStart','FricEnd','Side','Cycle','RFF_ST','ValidSide','Reject'});
end

function T = empty_mb_landmark_table()
T = table(strings(0,1),strings(0,1),strings(0,1),strings(0,1),strings(0,1),zeros(0,1),strings(0,1),zeros(0,1),strings(0,1),zeros(0,1),zeros(0,1),strings(0,1),strings(0,1),false(0,1),strings(0,1), ...
    'VariableNames',{'Method','Subject','Filename','Filepath','Token','Rep','Side','LandmarkIndex','LandmarkLabel','Time_s','SampleIndex','ChosenTrace','PulseSource','ValidSide','Reject'});
end

function T = empty_mb_qc_table()
T = table(strings(0,1),strings(0,1),strings(0,1),strings(0,1),strings(0,1),zeros(0,1),strings(0,1),false(0,1),strings(0,1),strings(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),strings(0,1),zeros(0,1),zeros(0,1),zeros(0,1),zeros(0,1),false(0,1),false(0,1),strings(0,1), ...
    'VariableNames',{'Method','Subject','Filename','Filepath','Token','Rep','Side','ValidSide','Reject','PulseSource','NCandidates','NAttemptedLandmarks','NFinalLandmarks','EdgeTime_s','EdgeGap_s','EdgeGap_ms','EdgeGapCycles','WrongSideCount','SkippedBoundaryCandidates','BoundaryAdjustmentReason','MedianPeriod_s','PeriodCV','MaxPeriodToMedianRatio','MaxAdjacentPeriodRatio','Contiguous','ManualReview','ReviewReason'});
end

function delete_if_exists(path)
try
    if exist(path,'file')
        delete(path);
    end
catch
end
end

function write_text_file(path, txt)
fid = fopen(path, 'w');
if fid < 0; error('Could not write file: %s', path); end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', txt);
end
