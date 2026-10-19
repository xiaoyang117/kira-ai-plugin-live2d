"""Build a small RMS envelope once on the host; clients follow playback position."""
from array import array
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

def levels(samples,rate,channels):
    frame=max(1,int(rate*.04))*channels
    amplitudes=[]
    for offset in range(0,len(samples),frame):
        part=samples[offset:offset+frame]
        amplitudes.append(math.sqrt(sum((value/32768)**2 for value in part)/max(1,len(part))))
    if not amplitudes:return {'step_ms':40,'levels':[]}
    reference=max(.035,sorted(amplitudes)[int((len(amplitudes)-1)*.95)])
    return {'step_ms':40,'levels':[round(min(1.,max(0.,(value-.008)/reference))**.65,3) for value in amplitudes]}

def envelope(path):
    path=Path(path)
    try:
        with wave.open(str(path),'rb') as audio:
            if audio.getsampwidth()!=2:raise ValueError('Decode through ffmpeg')
            rate=audio.getframerate();channels=audio.getnchannels();raw=audio.readframes(min(audio.getnframes(),rate*300))
        samples=array('h',raw)
        if sys.byteorder!='little':samples.byteswap()
        return levels(samples,rate,channels)
    except (OSError,ValueError,EOFError,wave.Error):
        executable=shutil.which('ffmpeg')
        if not executable:return {'step_ms':40,'levels':[]}
        try:
            result=subprocess.run([executable,'-v','error','-i',str(path),'-t','300','-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'],
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode or len(result.stdout)>5*1024*1024:return {'step_ms':40,'levels':[]}
            samples=array('h',result.stdout)
            if sys.byteorder!='little':samples.byteswap()
            return levels(samples,8000,1)
        except (OSError,subprocess.TimeoutExpired):return {'step_ms':40,'levels':[]}
