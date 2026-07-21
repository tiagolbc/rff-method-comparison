function output = plot_pulses(aRFF)
%define plotting colors
cmap = [70 193 164; 31 34 105; 151 24 129; 254 34 96; 253 210 69; 97 46 167]./255;

aRFF.trough_array = sort(aRFF.trough_array);
aRFF.peak_array = sort(aRFF.peak_array);

subplot(4,1,1); hold on;
plot(aRFF.t(aRFF.trough_array),aRFF.y(aRFF.trough_array),'.','MarkerSize',10,'Color',cmap(2,:));
plot(aRFF.t(aRFF.peak_array),aRFF.y( aRFF.peak_array),'.','MarkerSize',10,'Color',cmap(4,:));
xlim([aRFF.t(aRFF.trough_array(1))-0.05 aRFF.t(aRFF.trough_array(end))+0.05])

subplot(4,1,3); hold on;
plot(aRFF.t(aRFF.trough_array),aRFF.f0y(aRFF.trough_array),'.','MarkerSize',10,'Color',cmap(2,:));
plot(aRFF.t(aRFF.peak_array),aRFF.f0y(aRFF.peak_array),'.','MarkerSize',10,'Color',cmap(4,:));
xlim([aRFF.t(aRFF.trough_array(1))-0.05 aRFF.t(aRFF.trough_array(end))+0.05])

output = 1;