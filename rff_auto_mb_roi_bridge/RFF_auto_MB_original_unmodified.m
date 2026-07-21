% Clean the workspace and command window
clear;
clc;

% Check if temporary workspace file exists
if exist(['Dependencies' filesep 'tempWS.mat'], 'file') == 2
    % Load the temporary workspace if it exists
    load(['Dependencies' filesep 'tempWS.mat']);
else
    % If the temporary workspace doesn't exist, create it
    % EDIT audDir with the path to the wav files
    audDir = '/path/to/wavs/';
    
    % Define the path to the Praat application
    global praatPath;
    praatPath = '/Applications/Praat.app/Contents/MacOS/Praat'; % MAC
%     praatPath = 'Dependencies\Praat.exe'; % PC
    
    % Add the 'Dependencies' folder to the MATLAB search path
    addpath('Dependencies');
    
    % Get a list of WAV files in the specified directory
    files = dir([audDir, '*.wav']);
    
    % Read fricative locations from an Excel file
    fricLocs = readtable('/path/to/fricatives_locations.xlsx');
    
    % Initialize variables to store the analysis results
    file_count = numel(files);
    starti = 1;
    OFF_Reject = cell(file_count, 1);
    ON_Reject = cell(file_count, 1);
    Filename = cell(file_count, 1);
    OFF_pulse = zeros(file_count, 11);
    ON_pulse = zeros(file_count, 11);
end

%% Processing loop
nbytes = fprintf('processing 0 of %d', file_count);

% Loop through the files from 'starti' to 'file_count'
for ii = starti:file_count
    
    % Print the progress status indicating the file number being processed
    fprintf(repmat('\b',1,nbytes))
    nbytes = fprintf('Processing %d of %d...\n', ii, file_count);

    % Get the current file name from the 'files' struct
    fileName = files(ii).name;
    
    % Read the audio file and its sampling frequency
    [y, Fs] = audioread([audDir, fileName]);
    
    % Get the fricative location corresponding to the current file
    % IMPORTANT the fricative location spreadsheet should have two columns,
    % "Filename" and "FricLoc" which is the repsective fricative location
    % in seconds.
    fricLoc = fricLocs.FricLoc(matches(fricLocs.Filename, fileName));
    
    % Compute the fundamental frequency (f0) and its corresponding locations (f0Loc) in the audio
    [f0, f0Loc] = pitch(y, Fs);
    
    % Get the pulse information using Praat for the current audio file
    pulses = get_praat_pulse([audDir, fileName]);
    
    % Extract the 'off' and 'on' pulses using a sliding window and voting
    % method
    off_pulses = get_pulses_slide([audDir, fileName], fricLoc, pulses, 'off');
    on_pulses = get_pulses_slide([audDir, fileName], fricLoc, pulses, 'on');
    
    % Initialize variables to store rejection reasons and flags
    off_reject = '';
    on_reject = '';
    off_reject_flag = 0;
    on_reject_flag = 0;
    
    % Check if the number of 'off' pulses is less than 11
    if length(off_pulses) < 11
        off_reject_flag = 1;
        off_reject = 'not enough pulses';
    end
    
    % Check if the number of 'on' pulses is less than 11
    if length(on_pulses) < 11
        on_reject_flag = 1;
        on_reject = 'not enough pulses';
    end
    
    % Check if both 'off' and 'on' pulses exist and there is a long pause between them
    if off_reject_flag == 0 && on_reject_flag == 0
        if on_pulses(1) - off_pulses(end) > 0.25
            off_reject_flag = 1;
            off_reject = 'long pause between phonemes';
            on_reject_flag = 1;
            on_reject = 'long pause between phonemes';
        end
    end
    
    %% OFFSET SECTION
    % This section of the code performs various checks and validations on the 'off' pulses.
    
    procStep = 1;
    
    while procStep < 6 && off_reject_flag == 0
        % Loop through different processing steps (procStep) until reaching the maximum step or a rejection flag is raised.
        
        off_T = diff(off_pulses); % Calculate the time intervals between 'off' pulses.
        
        switch procStep
            
            case 1
                % Step 1: Check for vocal fry based on the median f0 in the 'off' region.
                
                off_f0 = f0(f0Loc./Fs < fricLoc & f0Loc./Fs > off_pulses(end-11)); % Extract f0 values during the 'off' region.
                
                if median(off_f0) < 100
                    % If the median f0 is below 100 Hz, reject due to vocal fry.
                    off_reject_flag = 1;
                    off_reject = 'vocal fry';
                end
                
                procStep = 2; % Move to the next processing step.
                
            case 2
                % Step 2: Check for outlier in the last 'off' pulse period.
                
                if off_T(end) > prctile(off_T(end-9:end), 65) * 1.5
                    % If the last 'off' pulse period is an outlier, remove it and recompute the time intervals.
                    off_pulses(end) = [];
                    off_T = diff(off_pulses);
                    if off_T(end) > prctile(off_T(end-9:end), 65) * 1.5
                        % If the new last 'off' pulse period is still an outlier, reject due to outlier period.
                        off_reject_flag = 1;
                        off_reject = 'offset period is an outlier';
                    end
                end
                
                procStep = 3; % Move to the next processing step.
                
            case 3
                % Step 3: Check for high variance in 'off' pulse periods.
                
                if var(off_T(end-9:end)) > 2.9e-6
                    % If the variance in the last ten 'off' pulse periods is high, reject due to high variance.
                    off_reject_flag = 1;
                    off_reject = 'high variance in periods';
                end
                
                procStep = 4; % Move to the next processing step.
                
            case 4
                % Step 4: Check for outliers in other 'off' pulse periods.
                
                if sum(off_T(end-9:end) > prctile(off_T(end-9:end), 65) * 1.5) > 0
                    % If any 'off' pulse periods contain an outlier, reject due to outlier periods.
                    off_reject_flag = 1;
                    off_reject = 'other onset periods contain an outlier';
                end
                
                procStep = 5; % Move to the next processing step.
                
            case 5
                % Step 5: Check for failure to reach steady-state in 'off' pulse periods.
                
                off_F = 1./off_T; % Calculate the frequencies of 'off' pulses.
                
                off_RFF = 12 .* log2(off_F(end-9:end) ./ off_F(end-9)); % Calculate the relative fundamental frequency (RFF) of 'off' pulses.
                
                if abs(off_RFF(2)) > 0.8
                    % If the RFF value of the second last 'off' pulse is greater than 0.8, reject due to failure to reach steady-state.
                    off_reject_flag = 1;
                    off_reject = 'failure to reach steady-state';
                end
                
                procStep = 6; % Move to the next processing step (This is the last step, so the loop will terminate).
                
        end
        
    end
    
    
    %% ONSET SECTION
    % This section of the code performs similar checks and validations on the 'on' pulses.
    
    procStep = 1;
    
    while procStep < 6 && on_reject_flag == 0
        % Loop through different processing steps (procStep) until reaching the maximum step or a rejection flag is raised.
        
        on_T = diff(on_pulses); % Calculate the time intervals between 'on' pulses.
        
        switch procStep
            
            case 1
                % Step 1: Check for vocal fry based on the median f0 in the 'on' region.
                
                on_f0 = f0(f0Loc./Fs > fricLoc & f0Loc./Fs < on_pulses(11)); % Extract f0 values during the 'on' region.
                
                if median(on_f0) < 100 && on_reject_flag == 0
                    % If the median f0 is below 100 Hz and no previous rejection, reject due to vocal fry.
                    on_reject_flag = 1;
                    on_reject = 'vocal fry';
                end
                
                procStep = 2; % Move to the next processing step.
                
            case 2
                % Step 2: Check for outlier in the first 'on' pulse period.
                
                if on_T(1) > prctile(on_T(1:10), 65) * 1.5
                    % If the first 'on' pulse period is an outlier, remove it and recompute the time intervals.
                    on_pulses(1) = [];
                    on_T = diff(on_pulses);
                    if on_T(1) > prctile(on_T(1:10), 65) * 1.5
                        % If the new first 'on' pulse period is still an outlier, reject due to outlier period.
                        on_reject_flag = 1;
                        on_reject = 'onset period is an outlier';
                    end
                end
                
                procStep = 3; % Move to the next processing step.
                
            case 3
                % Step 3: Check for high variance in 'on' pulse periods.
                
                if var(on_T(1:10)) > 2.9e-6
                    % If the variance in the first ten 'on' pulse periods is high, reject due to high variance.
                    on_reject_flag = 1;
                    on_reject = 'high variance in periods';
                end
                
                procStep = 4; % Move to the next processing step.
                
            case 4
                % Step 4: Check for outliers in other 'on' pulse periods.
                
                if sum(on_T(2:10) > prctile(on_T(1:10), 65) * 1.5) > 0
                    % If any 'on' pulse periods contain an outlier, reject due to outlier periods.
                    on_reject_flag = 1;
                    on_reject = 'other onset periods contain an outlier';
                end
                
                procStep = 5; % Move to the next processing step.
                
            case 5
                % Step 5: Check for failure to reach steady-state in 'on' pulse periods.
                
                on_F = 1./on_T; % Calculate the frequencies of 'on' pulses.
                
                on_RFF = 12 .* log2(on_F(1:10) ./ on_F(10)); % Calculate the relative fundamental frequency (RFF) of 'on' pulses.
                
                if abs(on_RFF(9)) > 0.8 && on_reject_flag == 0
                    % If the RFF value of the ninth 'on' pulse is greater than 0.8 and no previous rejection, reject due to failure to reach steady-state.
                    on_reject_flag = 1;
                    on_reject = 'failure to reach steady-state';
                end
                
                procStep = 6; % Move to the next processing step (This is the last step, so the loop will terminate).
                
        end
        
    end
    
    
    %% Save data for the current audio file (ii-th file)
    
    % Store the filename in the 'Filename' cell array
    Filename{ii, 1} = fileName;
    
    % Check if 'off' rejection flag is not raised (off_reject_flag = 0)
    if off_reject_flag == 0
        % If no 'off' rejection, save the last 11 'off' pulses in the 'OFF_pulse' matrix
        OFF_pulse(ii, :) = off_pulses(end-10:end);
    else
        % If 'off' rejection, set the 'OFF_pulse' to zeros and store the 'off' rejection reason in the 'OFF_Reject' cell array
        OFF_pulse(ii, :) = zeros(1, 11);
        OFF_Reject{ii, 1} = off_reject;
    end
    
    % Check if 'on' rejection flag is not raised (on_reject_flag = 0)
    if on_reject_flag == 0
        % If no 'on' rejection, save the first 11 'on' pulses in the 'ON_pulse' matrix
        ON_pulse(ii, :) = on_pulses(1:11);
    else
        % If 'on' rejection, set the 'ON_pulse' to zeros and store the 'on' rejection reason in the 'ON_Reject' cell array
        ON_pulse(ii, :) = zeros(1, 11);
        ON_Reject{ii, 1} = on_reject;
    end
    
    % Clear all variables except the ones required for the next iteration
    clearvars -except audDir files fricLocs file_count OFF_Reject ON_Reject starti ii Filename OFF_pulse ON_pulse
    
    % Save the current workspace variables to a temporary MAT file
    save(['Dependencies' filesep 'tempWS.mat'])
    
end

% Combine results into a table and save to an Excel file

% Combine the Filename, OFF_pulse, ON_pulse, OFF_Reject, and ON_Reject arrays into a table
rffout = splitvars(table(Filename, OFF_pulse, ON_pulse, OFF_Reject, ON_Reject));

% Save the table to an Excel file with a filename that includes the current date and time
% The filename format will be: 'RFF_results_yyyymmdd_HHMMSS.xlsx'
% For example: 'RFF_results_20230720_123456.xlsx'
writetable(rffout, [audDir, 'RFF_results_', datestr(clock, 'yyyymmdd_HHMMSS'), '.xlsx']);

% Delete the temporary workspace file that was created during processing
delete(['Dependencies' filesep 'tempWS.mat']);

% Display a message indicating that the process is completed
disp('done!');
