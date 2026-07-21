function pulses = get_praat_pulse_mb_native(fileName, fricLoc, offYN, filtYN)
% GET_PRAAT_PULSE_MB_NATIVE
% I/O-safe execution of the original MB Praat operations.
%
% The signal operations match the original get_praat_pulse.m and
% praat_pulse_array.praat: optional extraction before/after fricLoc, optional
% 60-3000 Hz Hann filtering, then PointProcess (periodic, cc) at 75-500 Hz.
% Only transport differs: pulse times are written to a temporary text file
% because Windows Praat does not reliably return Info-window text to system().
% Two execution modes are attempted:
%   1) an inline temporary Praat script with absolute paths embedded;
%   2) the command-line form script used in v9.
% It also tries a sibling praatcon.exe automatically when the selected path is
% Praat.exe. Pulse times are written to a temporary text file and read by
% MATLAB; no Info-window/stdout parsing is required for the primary path.

arguments
    fileName char
    fricLoc double = 0
    offYN double = 0
    filtYN double = 0
end

global MB_ROI_PRAAT_PATH
if isempty(MB_ROI_PRAAT_PATH)
    error('Global MB_ROI_PRAAT_PATH is empty. Supply praatPath to RFF_auto_MB_ROI_bridge.');
end

global MB_ROI_LAST_PRAAT_DEBUG
MB_ROI_LAST_PRAAT_DEBUG = struct('mode','','exe','','status',NaN,'stdout','','outTxt','','nPulses',0,'message','');

pulses = [];
exeCandidates = praat_exe_candidates(MB_ROI_PRAAT_PATH);

% First: inline script with the original crop semantics.
for ei = 1:numel(exeCandidates)
    [vals, dbg] = run_praat_inline(exeCandidates{ei}, fileName, fricLoc, offYN, filtYN);
    MB_ROI_LAST_PRAAT_DEBUG = dbg;
    if ~isempty(vals)
        pulses = finalize_pulses(vals);
        MB_ROI_LAST_PRAAT_DEBUG.nPulses = numel(pulses);
        return;
    end
end

% Second: v9-compatible form script. Kept as fallback for machines where
% Praat rejects inline scripts but accepts --run form arguments.
scriptPath = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'Dependencies', 'praat_pulse_array_mb_native.praat');
for ei = 1:numel(exeCandidates)
    [vals, dbg] = run_praat_form(exeCandidates{ei}, scriptPath, fileName, fricLoc, offYN, filtYN);
    MB_ROI_LAST_PRAAT_DEBUG = dbg;
    if ~isempty(vals)
        pulses = finalize_pulses(vals);
        MB_ROI_LAST_PRAAT_DEBUG.nPulses = numel(pulses);
        return;
    end
end

pulses = zeros(0,1);
end

function pulses = finalize_pulses(vals)
pulses = vals(:);
pulses = pulses(isfinite(pulses));
pulses = unique(sort(pulses));
end

function candidates = praat_exe_candidates(praatPath)
candidates = {};
if ~isempty(praatPath)
    candidates{end+1} = char(praatPath); %#ok<AGROW>
    [d,n,e] = fileparts(char(praatPath));
    if ~isempty(d)
        sibs = {'praatcon.exe','Praat.exe','praat.exe','praat'};
        for k = 1:numel(sibs)
            cand = fullfile(d, sibs{k});
            if exist(cand, 'file') && ~strcmpi(cand, praatPath)
                candidates{end+1} = cand; %#ok<AGROW>
            end
        end
    end
end
% De-duplicate while preserving order.
out = {};
for i = 1:numel(candidates)
    if exist(candidates{i}, 'file') || strcmpi(candidates{i}, 'praat') || strcmpi(candidates{i}, 'praatcon')
        if ~any(strcmpi(out, candidates{i}))
            out{end+1} = candidates{i}; %#ok<AGROW>
        end
    end
end
candidates = out;
end

function [vals, dbg] = run_praat_inline(praatExe, fileName, fricLoc, offYN, filtYN)
vals = [];
outTxt = [tempname, '.txt'];
scriptPath = [tempname, '.praat'];
cleanupObj = onCleanup(@() cleanup_files({outTxt, scriptPath})); %#ok<NASGU>
try
    script = build_inline_praat_script(fileName, outTxt, fricLoc, offYN, filtYN);
    write_text_file(scriptPath, script);
    cmd = sprintf('"%s" --run "%s"', praatExe, scriptPath);
    [status, stdout] = system(cmd);
    vals = read_numeric_lines(outTxt);
    dbg = make_debug('inline', praatExe, status, stdout, outTxt, vals, '');
catch ME
    dbg = make_debug('inline', praatExe, -999, ME.message, outTxt, vals, ME.message);
end
end

function [vals, dbg] = run_praat_form(praatExe, scriptPath, fileName, fricLoc, offYN, filtYN)
vals = [];
outTxt = [tempname, '.txt'];
cleanupObj = onCleanup(@() cleanup_files({outTxt})); %#ok<NASGU>
try
    cmd = sprintf('"%s" --run "%s" "%s" %.12g %.0f %.0f "%s"', ...
        praatExe, scriptPath, fileName, fricLoc, offYN, filtYN, outTxt);
    [status, stdout] = system(cmd);
    vals = read_numeric_lines(outTxt);
    if isempty(vals)
        vals = parse_numeric_stdout(stdout);
    end
    dbg = make_debug('form', praatExe, status, stdout, outTxt, vals, '');
catch ME
    dbg = make_debug('form', praatExe, -999, ME.message, outTxt, vals, ME.message);
end
end

function script = build_inline_praat_script(fileName, outTxt, fricLoc, offYN, filtYN)
name = praat_escape_path(fileName);
out = praat_escape_path(outTxt);
script = sprintf([ ...
'name$ = "%s"\n' ...
'outtxt$ = "%s"\n' ...
'fricloc = %.15g\n' ...
'offYN = %.0f\n' ...
'filtYN = %.0f\n' ...
'Read from file: name$\n' ...
'totalDuration = Get total duration\n' ...
'if fricloc > 0\n' ...
'    if offYN == 1\n' ...
'        Extract part: 0, fricloc, "rectangular", 1, "no"\n' ...
'    elsif offYN == 0\n' ...
'        Extract part: fricloc, totalDuration, "rectangular", 1, "no"\n' ...
'    endif\n' ...
'endif\n' ...
'if filtYN == 1\n' ...
'    Filter (pass Hann band): 60, 3000, 100\n' ...
'endif\n' ...
'To PointProcess (periodic, cc): 75, 500\n' ...
'numberOfPulses = Get number of points\n' ...
'if numberOfPulses > 0\n' ...
'    pulsei = Get time from index: 1\n' ...
'    writeFileLine: outtxt$, pulsei\n' ...
'    for ii from 2 to numberOfPulses\n' ...
'        pulsei = Get time from index: ii\n' ...
'        appendFileLine: outtxt$, pulsei\n' ...
'    endfor\n' ...
'else\n' ...
'    writeFileLine: outtxt$, ""\n' ...
'endif\n' ...
'exitScript()\n'], name, out, fricLoc, offYN, filtYN);
end

function p = praat_escape_path(p)
p = char(p);
p = strrep(p, '\\', '/');
p = strrep(p, '"', '""');
end

function vals = read_numeric_lines(path)
vals = [];
if ~exist(path, 'file')
    return;
end
fid = fopen(path, 'r');
if fid < 0
    return;
end
c = onCleanup(@() fclose(fid)); %#ok<NASGU>
while true
    line = fgetl(fid);
    if ~ischar(line)
        break;
    end
    v = str2double(strtrim(line));
    if isfinite(v)
        vals(end+1,1) = v; %#ok<AGROW>
    end
end
end

function vals = parse_numeric_stdout(txt)
vals = [];
if isempty(txt)
    return;
end
lines = regexp(char(txt), '\r\n|\n|\r', 'split');
for i = 1:numel(lines)
    s = strtrim(lines{i});
    if isempty(s)
        continue;
    end
    v = str2double(s);
    if isfinite(v)
        vals(end+1,1) = v; %#ok<AGROW>
    end
end
end

function dbg = make_debug(mode, exe, status, stdout, outTxt, vals, message)
dbg = struct();
dbg.mode = string(mode);
dbg.exe = string(exe);
dbg.status = double(status);
dbg.stdout = string(first_chars(stdout, 2000));
dbg.outTxt = string(outTxt);
dbg.outFileExists = exist(outTxt, 'file') == 2;
dbg.nPulses = numel(vals);
dbg.message = string(message);
end

function s = first_chars(txt, n)
s = char(txt);
if numel(s) > n
    s = s(1:n);
end
end

function cleanup_files(paths)
for i = 1:numel(paths)
    try
        if exist(paths{i}, 'file')
            delete(paths{i});
        end
    catch
    end
end
end

function write_text_file(path, txt)
fid = fopen(path, 'w');
if fid < 0
    error('Could not write temporary Praat script: %s', path);
end
c = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid, '%s', txt);
end
