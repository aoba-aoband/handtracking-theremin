"""Render actual SC DSP offline and measure stereo Thru, tails, mute and modulation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import wave
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gui.regular.transport import ROOT
from gui.regular.process_scope import ProcessScope


def read(path):
    with wave.open(str(path),'rb') as source:
        assert source.getnchannels()==2 and source.getsampwidth()==2
        return np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').reshape(-1,2).astype(float)/32768


def write(path,signal,rate=48000):
    with wave.open(str(path),'wb') as output:
        output.setnchannels(2); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes((np.clip(signal,-1,1)*32767).astype('<i2').tobytes())


def analytic(signal):
    n=len(signal); weights=np.zeros(n); weights[0]=1
    weights[1:(n+1)//2]=2
    if n%2==0: weights[n//2]=1
    return np.fft.ifft(np.fft.fft(signal)*weights)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sclang',default='C:/Program Files/SuperCollider-3.14.1/sclang.exe')
    args=parser.parse_args()
    folder=ROOT/'analysis/effects-signal'; folder.mkdir(parents=True,exist_ok=True)
    t=np.arange(48000*3)/48000
    reference=np.column_stack((.07*np.sin(2*np.pi*440*t),.05*np.sin(2*np.pi*990*t)))
    write(folder/'input.wav',reference)
    scope=ProcessScope()
    try:
        with (folder/'render.log').open('w',encoding='utf-8') as log:
            process=scope.launch([args.sclang,'-D',str(ROOT/'tests/sc_effects_signal.scd')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            result=process.wait(timeout=120)
    finally: scope.close()
    assert result==0, 'SC render failed; inspect analysis/effects-signal/render.log'
    sounds={key:read(folder/(key+'.wav')) for key in ('thru','internal','distortion','fuzz','delay_tail','reverb_tail','vibrato','tremolo','subtractive','distortion_high','fuzz_high')}
    report={}
    for key,signal in sounds.items():
        active=signal[24000:86400]
        report[key]={'rms':float(np.sqrt(np.mean(active**2))),'peak':float(np.max(np.abs(signal))),
                     'dc':np.mean(active,axis=0).tolist(),'after_panic_peak':float(np.max(np.abs(signal[97000:]))) }
        assert np.isfinite(signal).all() and np.max(np.abs(signal))<=.981
        assert report[key]['after_panic_peak'] == 0, key+' PANIC leaked audio'
    thru=sounds['thru']
    # Safety DC blocker adds a small phase shift; fit sin/cos per independent
    # channel to separate stereo crosstalk from phase and limiter lookahead.
    tt=np.arange(24000,86400)/48000
    basis=np.column_stack([np.sin(2*np.pi*f*tt) for f in (440,990)]+[np.cos(2*np.pi*f*tt) for f in (440,990)])
    fit=np.linalg.lstsq(basis,thru[24000:86400],rcond=None)[0]
    left=np.hypot(fit[0,0],fit[2,0]); right=np.hypot(fit[1,1],fit[3,1])
    cross=max(np.hypot(fit[1,0],fit[3,0]),np.hypot(fit[0,1],fit[2,1]))
    report['thru'].update(left_amplitude=float(left),right_amplitude=float(right),crosstalk=float(cross))
    assert abs(left-.07)<.001 and abs(right-.05)<.001 and cross<.00005
    assert report['internal']['rms']>.01
    for key in ('delay_tail','reverb_tail'):
        tail=sounds[key][28800:48000]
        rms=float(np.sqrt(np.mean(tail**2))); report[key]['tail_rms']=rms
        assert rms>.00005, key+' normal bypass cut the tail'
    a=sounds['distortion'][24000:86400,0]; b=sounds['fuzz'][24000:86400,0]
    a=a/np.sqrt(np.mean(a*a)); b=b/np.sqrt(np.mean(b*b))
    difference=float(np.sqrt(np.mean((a-b)**2))); report['level_matched_distortion_fuzz_difference']=difference
    assert difference>.04
    for key in ('distortion','fuzz'):
        signal=sounds[key][24000:86400,0]
        spectrum=np.abs(np.fft.rfft(signal*np.hanning(len(signal))))**2
        frequencies=np.fft.rfftfreq(len(signal),1/48000)
        report[key]['energy_above_12k_ratio']=float(spectrum[frequencies>12000].sum()/spectrum.sum())
        assert abs(report[key]['dc'][0])<.002
    for key in ('distortion_high','fuzz_high'):
        signal=sounds[key][24000:86400,0]
        spectrum=np.abs(np.fft.rfft(signal*np.hanning(len(signal))))**2
        frequencies=np.fft.rfftfreq(len(signal),1/48000)
        harmonic=np.zeros(len(spectrum),dtype=bool)
        for f in (5000,10000,15000,20000): harmonic|=abs(frequencies-f)<20
        harmonic|=frequencies<20
        report[key]['off_harmonic_energy_ratio']=float(spectrum[~harmonic].sum()/spectrum.sum())
        report[key]['measurement_note']='5 kHz/high-drive alias-plus-spurious proxy, not a guarantee of alias-free audio; no oversampling'
    signal=sounds['vibrato'][24000:86400,0]
    phase=np.unwrap(np.angle(analytic(signal)))
    pitch=np.diff(phase)*48000/(2*np.pi)
    cents=1200*np.log2(np.maximum(1,pitch)/440)[4800:-4800]
    report['vibrato']['cents_p05_p95']=np.percentile(cents,[5,95]).tolist()
    assert np.percentile(cents,95)>25 and np.percentile(cents,95)<45
    assert np.percentile(cents,5)<-25
    gain=np.abs(analytic(sounds['tremolo'][24000:86400,0]))[4800:-4800]
    ratio=float(np.percentile(gain,5)/np.percentile(gain,95)); report['tremolo']['min_max_amplitude_ratio']=ratio
    assert .35<ratio<.5
    # Level-matched examples for optional human listening. Never auto-play.
    for key in ('distortion','fuzz'):
        signal=sounds[key][:96000]
        signal=signal*(.08/max(.001,np.sqrt(np.mean(signal[24000:86400]**2))))
        write(folder/(key+'-level-matched.wav'),signal)
    (folder/'measurements.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    print('PASS production DSP: stereo Thru bypass, immediate PANIC, delay/reverb tails, distinct level-matched distortion/fuzz, vibrato and tremolo')


if __name__=='__main__': main()
