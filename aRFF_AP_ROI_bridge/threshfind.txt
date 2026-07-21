function threshvalue = threshfind(vector)
%function is used to find the threshold that maximizes the effect size of a
%vector. The vector is a vector of values from one distribution on the left side
%and values from another distribution on the right side
l = length(vector);
if l  > 4
    vector_sm = smooth(vector,5);
    vector_sm(1) = vector_sm(2);
    vector_sm(end) = vector_sm(end-1);
else 
    vector_sm = vector;
end
if vector(1) > vector(end)
    [a,numnotcycle] =  min(diff(vector_sm));
else
    [a,numnotcycle] =  max(diff(vector_sm));
end

if size(vector,1) < 2
    vector = vector';
end

numcycle = l-numnotcycle;
meancycle = mean(vector(end-numcycle+1:end));
meannotcycle = mean(vector(1:numnotcycle));
stdcycle = std(vector(end-numcycle+1:end));
stdnotcycle = std(vector(1:numnotcycle));

if stdnotcycle == stdcycle
    threshvalue = mean([meancycle meannotcycle]);
else
    threshvalue = (meancycle*stdnotcycle + meannotcycle*stdcycle)/(stdnotcycle+stdcycle);
end