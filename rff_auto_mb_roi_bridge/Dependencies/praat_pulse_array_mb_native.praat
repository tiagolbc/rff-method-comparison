form Voice_analysis
    text name ""
    real fricloc 0
    real offYN 0
    real filtYN 0
    text outtxt ""
endform

Read from file: name$
totalDuration = Get total duration

# Preserve the original MB extraction semantics and local timebase.
if fricloc > 0
    if offYN == 1
        Extract part: 0, fricloc, "rectangular", 1, "no"
    elsif offYN == 0
        Extract part: fricloc, totalDuration, "rectangular", 1, "no"
    endif
endif

if filtYN == 1
    Filter (pass Hann band): 60, 3000, 100
endif

To PointProcess (periodic, cc): 75, 500
numberOfPulses = Get number of points

# File output replaces only the original Info-window transport.
if outtxt$ <> "" and numberOfPulses > 0
    pulsei = Get time from index: 1
    writeFileLine: outtxt$, pulsei
    for ii from 2 to numberOfPulses
        pulsei = Get time from index: ii
        appendFileLine: outtxt$, pulsei
    endfor
else
    for ii from 1 to numberOfPulses
        pulsei = Get time from index: ii
        appendInfoLine: pulsei
    endfor
endif

exitScript()
