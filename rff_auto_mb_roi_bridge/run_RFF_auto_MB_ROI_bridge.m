% run_RFF_auto_MB_ROI_bridge.m
% Example runner. Edit the three paths below or call RFF_auto_MB_ROI_bridge
% directly from MATLAB/Python using matlab -batch.

manifestPath = fullfile(pwd, 'examples', 'example_roi_manifest.csv');
outDir = fullfile(pwd, 'example_output');

% macOS example:
praatPath = '/Applications/Praat.app/Contents/MacOS/Praat';

% Windows example:
% praatPath = 'C:\Program Files\Praat\Praat.exe';

RFF_auto_MB_ROI_bridge(manifestPath, outDir, praatPath);
