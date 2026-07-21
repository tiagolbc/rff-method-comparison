function output_files = run_arff_ap_roi_bridge(manifest_path, output_dir, algorithm_dir)
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% RUN_ARFF_AP_ROI_BRIDGE.M
%
% ROI-controlled aRFF-AP bridge for Python/MATLAB integration.
%
% Required manifest columns:
%   Filepath, FricStart, FricEnd
%
% Optional columns:
%   Subject, Filename, Token, Rep, FricLoc
%
% v16 preservation policy:
%   * automatic fricative localization is replaced by FricStart/FricEnd;
%   * original AP vowel conditioning and cycle extraction are retained;
%   * the unmodified original RFFoutput.m determines all RFF values and
%     rejection codes;
%   * ROI boundary checks are exported as QC only and never alter validity.
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

if nargin < 1 || isempty(manifest_path)
    error('manifest_path is required.');
end
if nargin < 2 || isempty(output_dir)
    output_dir = fullfile(pwd, 'arff_ap_roi_output');
end
if nargin < 3 || isempty(algorithm_dir)
    algorithm_dir = fileparts(mfilename('fullpath'));
end

manifest_path = char(manifest_path);
output_dir    = char(output_dir);
algorithm_dir = char(algorithm_dir);

if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end
work_audio_dir = fullfile(output_dir, '_arff_ap_roi_work_audio');
if ~exist(work_audio_dir, 'dir')
    mkdir(work_audio_dir);
end

% Globals used by original aRFF-AP code.
global min_pitch_set;
global max_pitch_set;
global maxpkn;
global perform_fol;
global stimulicomb;
min_pitch_set = 50;
max_pitch_set = 400;
stimulicomb   = 0;
perform_fol   = ensure_trailing_filesep(fullfile(output_dir, 'aRFF_internal'));
if ~exist(perform_fol, 'dir')
    mkdir(perform_fol);
end

addpath(algorithm_dir);
addpath(fullfile(algorithm_dir, 'dependencies'));
addpath(fullfile(algorithm_dir, 'dependencies', 'swipe'));

manifest = readtable(manifest_path, 'VariableNamingRule', 'preserve', 'Delimiter', ',');
manifest = standardize_manifest(manifest);
if ~ismember('Filepath', manifest.Properties.VariableNames) || ~ismember('FricStart', manifest.Properties.VariableNames) || ~ismember('FricEnd', manifest.Properties.VariableNames)
    error('Manifest must contain Filepath, FricStart, and FricEnd columns.');
end

% Exclude rows marked for exclusion if present, e.g., fourth repetition.
if ismember('UseForAnalysis', manifest.Properties.VariableNames)
    keep = logical(manifest.UseForAnalysis);
    manifest = manifest(keep,:);
end
if ismember('Exclude', manifest.Properties.VariableNames)
    drop = logical(manifest.Exclude);
    manifest = manifest(~drop,:);
end

% Create safe unique working filenames, one per unique original audio path.
orig_paths = string(manifest.Filepath);
unique_paths = unique(orig_paths, 'stable');
bridge_filename = strings(height(manifest),1);
bridge_subject  = strings(height(manifest),1);
for i = 1:numel(unique_paths)
    orig = char(unique_paths(i));
    if ~exist(orig, 'file')
        error('Audio file not found: %s', orig);
    end
    [~, stem, ext] = fileparts(orig);
    subj = '';
    token = '';
    idx_rows = find(orig_paths == unique_paths(i));
    if ismember('Subject', manifest.Properties.VariableNames)
        subj = char(string(manifest.Subject(idx_rows(1))));
    end
    if ismember('Token', manifest.Properties.VariableNames)
        token = char(string(manifest.Token(idx_rows(1))));
    end
    % Original RFFoutput.m uses the working stem as an Excel sheet name;
    % therefore it must stay within Excel's 31-character limit.
    safe_base = safe_name(strjoin_nonempty({subj, token}, '_'));
    if numel(safe_base) > 25
        safe_base = safe_base(1:25);
    end
    safe_stem = sprintf('%s_%04d', safe_base, i);
    if isempty(ext)
        ext = '.wav';
    end
    bfile = [safe_stem ext];
    copyfile(orig, fullfile(work_audio_dir, bfile));
    bridge_filename(idx_rows) = string(bfile);
    bridge_subject(idx_rows) = string(safe_stem);
end
manifest.BridgeFilename = bridge_filename;
manifest.BridgeSubject  = bridge_subject;
if ~ismember('FricLoc', manifest.Properties.VariableNames)
    manifest.FricLoc = (manifest.FricStart + manifest.FricEnd) ./ 2;
end
[~,~,gidx] = unique(manifest.BridgeFilename, 'stable');
counts = accumarray(gidx, 1);
maxpkn = max(counts);
if isempty(maxpkn) || maxpkn < 1
    maxpkn = 1;
end

bridge_manifest_path = fullfile(output_dir, 'rff_arff_ap_roi_manifest_used.csv');
writetable(manifest, bridge_manifest_path);

allfiles = dir(fullfile(work_audio_dir, '*.wav'));
if isempty(allfiles)
    % also accept other extensions after copy.
    allfiles = dir(fullfile(work_audio_dir, '*.*'));
    allfiles = allfiles(~[allfiles.isdir]);
end

native_workbook = fullfile(perform_fol,'aRFF.xlsx');
if exist(native_workbook,'file')
    delete(native_workbook);
end

fprintf('v16 native-preserving aRFF-AP ROI bridge: %d audio files, %d ROI rows.\n', length(allfiles), height(manifest));
for filei = 1:length(allfiles)
    filename = allfiles(filei).name;
    fprintf('[%d/%d] %s: F0 contour...\n', filei, length(allfiles), filename);
    find_contours_aswipep(ensure_trailing_filesep(work_audio_dir), filename);
    fprintf('[%d/%d] %s: ROI fricative parameters...\n', filei, length(allfiles), filename);
    find_fric_roi_native(ensure_trailing_filesep(work_audio_dir), filename, manifest);
    fprintf('[%d/%d] %s: AP cycle extraction...\n', filei, length(allfiles), filename);
    find_RFFcycles_aswipep_roi_native(ensure_trailing_filesep(work_audio_dir), filename, false);
end

fprintf('Running unmodified original aRFF-AP RFFoutput.m...\n');
RFFoutput(allfiles);
[wide_table, long_table, debug_table, landmark_table, cycle_qc_table] = ...
    RFFoutput_native_bridge(allfiles, manifest, output_dir, native_workbook); %#ok<ASGLU>

config = struct();
config.version = 'v16 Native AP + external ROI';
config.algorithm = 'original aRFF-AP with FricStart/FricEnd input adapter';
config.algorithm_dir = algorithm_dir;
config.manifest_path = manifest_path;
config.output_dir = output_dir;
config.min_pitch_set = min_pitch_set;
config.max_pitch_set = max_pitch_set;
config.boundary_mode = 'manual ROI: FricStart for offset, FricEnd for onset';
config.result_authority = 'unmodified dependencies/RFFoutput.m workbook';
config.automatic_fricative_detection = false;
config.native_rejection_codes_only = true;
config.created = datestr(now, 30);
config.cycle_qc = struct('exact_final_landmarks',11,'wrong_side_rejected',false,'hard_maximum_edge_gap_seconds',[], ...
    'edge_gap_review_seconds',0.10,'exports_candidates',true,'exports_skipped_boundary_candidates',true, ...
    'true_adjacent_period_ratio',true,'period_to_median_ratio_exported_separately',true, ...
    'policy','observational_only_does_not_change_native_AP_validity');
try
    fid = fopen(fullfile(output_dir, 'rff_arff_ap_roi_config.json'), 'w');
    fprintf(fid, '%s', jsonencode(config));
    fclose(fid);
catch
end

output_files = struct();
output_files.wide_csv = fullfile(output_dir, 'rff_arff_ap_roi_results_wide.csv');
output_files.long_csv = fullfile(output_dir, 'rff_arff_ap_roi_cycles_long.csv');
output_files.debug_csv = fullfile(output_dir, 'rff_arff_ap_roi_debug.csv');
output_files.landmarks_csv = fullfile(output_dir, 'rff_arff_ap_roi_landmarks_long.csv');
output_files.cycle_qc_csv = fullfile(output_dir, 'rff_arff_ap_roi_cycle_qc.csv');
output_files.manifest_used = bridge_manifest_path;
output_files.config_json = fullfile(output_dir, 'rff_arff_ap_roi_config.json');
end

function T = standardize_manifest(T)
% Handle common names from AVHI/Python exports.
vars = T.Properties.VariableNames;
T = rename_if_present(T, vars, {'Path','AudioPath','AudioFile','File'}, 'Filepath');
T = rename_if_present(T, T.Properties.VariableNames, {'Start','FricativeStart','FricStart_s'}, 'FricStart');
T = rename_if_present(T, T.Properties.VariableNames, {'End','FricativeEnd','FricEnd_s'}, 'FricEnd');
T = rename_if_present(T, T.Properties.VariableNames, {'FricativeLocation','FricLoc_s','Location'}, 'FricLoc');
if ismember('Filepath', T.Properties.VariableNames)
    T.Filepath = string(T.Filepath);
end
if ismember('FricStart', T.Properties.VariableNames)
    T.FricStart = double(T.FricStart);
end
if ismember('FricEnd', T.Properties.VariableNames)
    T.FricEnd = double(T.FricEnd);
end
if ismember('Rep', T.Properties.VariableNames)
    T.Rep = double(T.Rep);
end
end

function T = rename_if_present(T, vars, candidates, target)
if ismember(target, T.Properties.VariableNames)
    return;
end
for i = 1:numel(candidates)
    c = candidates{i};
    if ismember(c, vars)
        T.Properties.VariableNames{strcmp(T.Properties.VariableNames,c)} = target;
        return;
    end
end
end

function s = ensure_trailing_filesep(s)
if isempty(s)
    return;
end
if s(end) ~= filesep
    s = [s filesep];
end
end

function out = safe_name(s)
s = char(s);
s = regexprep(s, '[^A-Za-z0-9_\-]+', '_');
s = regexprep(s, '_+', '_');
s = regexprep(s, '^_+|_+$', '');
if isempty(s)
    s = 'audio';
end
out = s;
end

function out = strjoin_nonempty(parts, sep)
keep = {};
for i = 1:numel(parts)
    p = char(string(parts{i}));
    if ~isempty(p) && ~strcmpi(p,'missing') && ~strcmpi(p,'nan')
        keep{end+1} = p; %#ok<AGROW>
    end
end
out = strjoin(keep, sep);
end
