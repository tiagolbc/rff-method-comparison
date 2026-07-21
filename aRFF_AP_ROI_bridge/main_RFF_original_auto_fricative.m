%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% MAIN_RFF.M estimates RFF using Auditory-SWIPE' and accounts for sample
% characteristics using the acoustic measure, pitch strength.
%
% Author: Jenny Vojtech (jmvo@bu.edu)
%         Stepp Lab, Boston University, MA
% Last Updated:   07/11/2024
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% DO NOT CHANGE %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
close all; clear; clc;

global min_pitch_set;
global max_pitch_set;
global maxpkn;
global perform_fol;
global stimulicomb;

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% SET THE FOLLOWING PARAMETERS: %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
min_pitch_set = 50;    %default min pitch is 50 Hz
max_pitch_set = 400;   %default max pitch is 400 Hz
maxpkn        = 3;     %initially assume that there will be 3 VCVs
stimulicomb   = 0;     %if RFF stimuli (e.g., /afa/, /ifi/, ufu/) are
%recorded separately, but you want the results combined into one file 
%under the speaker ID, then set stimulicomb to 1; otherwise, set it to 0

folname       = 'PATH\TO\SOUND\FILES\';  %path to sound files
algorithm     = 'PATH\TO\ALGORITHM\';	%path to where you downloaded aRFF
perform_fol   = 'PATH\TO\OUTPUT\'; 	%path to output folder
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% DO NOT CHANGE %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
cd(algorithm);
addpath('./dependencies/');
addpath('./dependencies/swipe');

allfiles = dir([folname '*.wav']);

g = waitbar(0, '');
load_screen = {'F0 Contour', 'Fric Detection', 'RFF Calculation'};
RFFout_check = zeros(length(allfiles), 1);
for k = 1:3
    for filei = 1:length(allfiles)
        waitbar(filei/length(allfiles),g,sprintf([load_screen{k}, ...
            ' for File %i/%i'],filei,length(allfiles)));
        filename = allfiles(filei).name;
        out_fol   = fullfile(perform_fol, filename(1:end-4), 'var');
        f0_file   = fullfile(out_fol, 'f0c_param.mat');
        fric_file = fullfile(out_fol, 'fric_param.mat');

        switch k
            case 1 %find the F0 & pitch strength contours and SNR
                if ~exist(f0_file, 'file')
                    find_contours_aswipep(folname,filename);
                end
            case 2 %find the location of fricatives
                if ~exist(fric_file, 'file')
                    adjust = false;
                    load_in = true;
                    find_fric_aswipep(folname, filename);
                end
            case 3 %find glottal cycles for RFF estimation
                find_RFFcycles_aswipep(folname,filename,false);
        end
        RFFout_check(filei) = k;
    end
end
close(g);
RFFoutput(allfiles);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

% RFF REJECTION LEGEND %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%0 = not rejected
%1 = too few periodic cycles (pre-process rejection)
%2 = fails to reach steady state or unstable
%3 = glottalized
%4 = aperiodic or irregular
%5 = sharp transition
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
