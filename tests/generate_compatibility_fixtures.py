"""Deterministic public engineering signals; no participant audio is used.

The two pitch rates exercise different cycle lengths. These simple acoustic
signals are compatibility fixtures, not validated male/female voice models.
"""
from pathlib import Path
import math,random,wave,struct,csv,argparse
def generate(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);rows=[];fs=44100
 for hz in [130,240]:
  rng=random.Random(20261116+hz);samples=[];start=.48;end=.63
  for i in range(round(1.15*fs)):
   t=i/fs
   if start<=t<end:y=.035*rng.uniform(-1,1)
   else:
    # A fixed harmonic mixture, with silence outside the two vowel intervals.
    local=t if t<start else t-end
    y=sum(math.sin(2*math.pi*hz*h*local+.11*h)/h**1.5 for h in range(1,21))*.28
    if t<.04 or t>=1.10:y=0
   # A deterministic low noise floor avoids the undefined 0/0 spectral ratio
   # in the original AP conditioning of perfectly silent stretches.
   y+=.00015*rng.uniform(-1,1)
   samples.append(max(-32767,min(32767,round(y*32767))))
  p=out/f'F{hz}_afa.wav'
  with wave.open(str(p),'wb') as w:w.setparams((1,2,fs,0,'NONE','not compressed'));w.writeframes(struct.pack('<'+'h'*len(samples),*samples))
  rows.append(dict(Filepath=str(p.resolve()),Subject=f'F{hz}',Filename=p.name,Token='afa',Rep=1,FricStart=start,FricEnd=end))
 with (out/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 return rows
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('out');generate(p.parse_args().out)
