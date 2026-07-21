function out_pulses = get_pulses_slide(fileName, fricLoc, pulses, on_off)
    % GET_PULSES_BOOT extracts glottal pulses using Praat with a sliding window for more precise pulse extraction.
    % This function is designed to work with an audio file and pulse information.
    %
    % INPUTS:
    %   fileName: The name of the audio file.
    %   fricLoc: A parameter for Praat specifying the location of fricative in seconds.
    %   pulses: An array of pulse data (double).
    %   on_off: A string specifying the type of pulses to be extracted ('on' or 'off').
    %
    % OUTPUTS:
    %   out_pulses: An array containing the extracted pulses.
    
    % Get information about the audio file without loading it into memory
    audioInfo = audioinfo(fileName);
    
    % Extract the file length (duration) and sampling frequency
    Fs = audioInfo.SampleRate;
    fileLength = audioInfo.Duration * Fs;
    
    off_pulses = pulses(pulses < fricLoc);
    on_pulses = pulses(pulses > fricLoc);
    pulses_all = [];
    winsiz = 0.01;
    pp = 0;

    switch on_off
        case 'off'
            x2 = ceil((on_pulses(1)) * Fs);
            
            % Calculate a safe starting point for pulse extraction
            if length(off_pulses) > 20
                xst = floor((off_pulses(end - 19) - (on_pulses(1) - off_pulses(end))) * Fs);
            else
                xst = 0;
            end
            
            if xst < 1
                x1 = 1;
            else
                x1 = xst;
            end

            % Loop through the audio file and extract pulses
            while x2 / Fs <= on_pulses(1)
                pp = pp + 1;
                temppulses = get_praat_pulse(fileName, fricLoc, 1, 0);
                if length(temppulses) > 15
                    pulses_all = [pulses_all; temppulses(end-14:end) + round(x1/Fs, 3)];
                end

                clear temppulses
                x1 = x1 + floor(winsiz * Fs);
                x2 = x2 + floor(winsiz * Fs);
            end

            % Perform voting on extracted pulses and assign to output
            if ~isempty(pulses_all)
                rpa = round(pulses_all, 3);
                upa = unique(rpa);
                for uu = 1:length(upa)
                    vpa(uu) = sum(rpa == upa(uu));
                end
                upa(vpa < 0.5 * pp) = [];
                if ~isempty(upa)
                    [~, mloc] = min(abs(off_pulses - upa(end)));
                    out_pulses = off_pulses(1:mloc);
                else
                    out_pulses = off_pulses;
                end
            else
                out_pulses = off_pulses;
            end

        case 'on'

            x1 = floor(off_pulses(end) * Fs);
            
            % Calculate the end point for pulse extraction
            if length(on_pulses) >= 20
                x2 = ceil(on_pulses(20) * Fs);
            else
                x2 = ceil(on_pulses(end) * Fs);
            end

            % Loop through the audio file and extract pulses
            while x1 / Fs <= on_pulses(1) - 0.02
                pp = pp + 1;

                temppulses = get_praat_pulse(fileName, fricLoc, 0, 0);
                if length(temppulses) > 20
                    pulses_all = [pulses_all; temppulses + round(x1 / Fs, 3)];
                end

                clear temppulses

                x1 = x1 + floor(winsiz * Fs);
                x2 = x2 + floor(winsiz * Fs);
                
                % Check if the end point exceeds the file length and adjust it
                if x2 > fileLength
                    x2 = fileLength;
                end
            end

            % Perform voting on extracted pulses and assign to output
            if ~isempty(pulses_all)
                rpa = round(pulses_all, 3);
                upa = unique(rpa);
                for uu = 1:length(upa)
                    vpa(uu) = sum(rpa == upa(uu));
                end
                upa(vpa < 0.3 * pp) = [];
                if ~isempty(upa)
                    [~, mloc] = min(abs(on_pulses - upa(1)));
                    out_pulses = on_pulses(mloc:end);
                else
                    out_pulses = on_pulses;
                end
            else
                out_pulses = on_pulses;
            end
    end
end
