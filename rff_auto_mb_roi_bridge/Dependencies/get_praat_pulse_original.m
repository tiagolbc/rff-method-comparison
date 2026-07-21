function pulses = get_praat_pulse(fileName, fricLoc, offYN, filtYN)
% GET_PRAAT_PULSE extracts pulse data from Praat for a given file.
% 
% INPUTS:
%   fileName: The name of the audio file including path.
%   praatPath: The path to Praat. Typically for Windows this will be
%   Praat.exe placed in the 'private' dependencies folder and for Mac this
%   will be /Applications/Praat.app/Contents/MacOS/Praat'
%
%   Optional:
%       fricLoc: A parameter for Praat specifying the location of fricative in seconds.
%       offYN: A parameter for Praat specifying whether to use extract
%       pulses before fricLoc (1) or after fricLoc (0). If fricLoc = 0,
%       this will be ignored.
%       filtYN: A parameter for Praat specifying whether to use filtered points (0 or 1).
%
% OUTPUTS:
%   pulses: An array containing the extracted pulse data.

% Default Arguments
arguments
    fileName char;
    fricLoc = 0;
    offYN = 0;
    filtYN = 0;
end

global praatPath

% Call Praat script to extract pulse data
[~, w] = system([praatPath,' --run ',cd,filesep,'Dependencies',filesep,...
    'praat_pulse_array.praat',' ',fileName,' ',...
    num2str(fricLoc),' ',num2str(offYN),' ',num2str(filtYN)]);

% Find line breaks in the output from Praat
lineBreaks = regexp(w, '[\n]');

% Extract the first value (number of pulses) from the output
pulses = str2double(w(1:lineBreaks(1) - 1));

% Loop through the output to extract the remaining pulse data
for lb = 2:length(lineBreaks)
    pulses(lb, 1) = str2double(w(lineBreaks(lb - 1) + 1:lineBreaks(lb) - 1));
end
