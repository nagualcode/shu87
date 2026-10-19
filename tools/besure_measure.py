"""Non-linear / stereo / CPU measurements of BESURE-N87 vs Shu87 via tools/auhost.c.

    python3 -I tools/besure_measure.py <workdir containing the built auhost>
"""
import numpy as np, subprocess, sys
W=sys.argv[1]; H=W+'/auhost'; sr=48000
def run(which,x,block=512,extra=()):
    x.astype(np.float32).tofile(W+'/nl_in.f32')
    cmd=[H]+(['aufx','Bes1','Anob'] if which=='B' else ['aufx','Shu8','JdSn'])+[str(sr),str(block),W+'/nl_in.f32',W+'/nl_out.f32',*extra]
    if which=='B': cmd=['arch','-x86_64']+cmd
    r=subprocess.run(cmd,capture_output=True,text=True)
    return np.fromfile(W+'/nl_out.f32',np.float32).reshape(-1,2), r.stderr.strip().splitlines()[-1]
def thd(y,f0):
    s=y[sr//2:sr//2+sr,0].astype(float)*np.hanning(sr); S=np.abs(np.fft.rfft(s))
    h=[S[int(round(k*f0))-2:int(round(k*f0))+3].max() for k in range(1,8)]
    return 100*np.sqrt(sum(v*v for v in h[1:]))/h[0], 100*h[1]/h[0], 100*h[2]/h[0]
t=np.arange(int(1.6*sr))/sr
print('THD (%)            level   total   H2     H3')
for which in 'BS':
    for f0 in (100,1000):
        for db in (-24,-12,-6,0):
            a=10**(db/20); x=np.zeros((len(t),2)); x[:,0]=a*np.sin(2*np.pi*f0*t); x[:,1]=x[:,0]
            y,_=run(which,x); T,h2,h3=thd(y,f0)
            print(f"{'BESURE' if which=='B' else 'Shu87 '} {f0:5d} Hz {db:+4d} dBFS {T:7.3f} {h2:6.3f} {h3:6.3f}")
# hot transient: decaying 80 Hz burst peaking at +3 dBFS (vocal plosive on a hot preamp)
x=np.zeros((sr,2)); n=np.arange(4000); x[1000:5000,0]=1.41*np.sin(2*np.pi*80*n/sr)*np.exp(-n/1500); x[:,1]=x[:,0]
for which in 'BS':
    y,_=run(which,x); print(('BESURE' if which=='B' else 'Shu87 '),'+3 dBFS plosive -> output peak', float(np.abs(y).max()), 'finite:',bool(np.isfinite(y).all()))
# stereo: signal only on the right input
x=np.zeros((sr,2)); x[:,1]=0.1*np.sin(2*np.pi*1000*np.arange(sr)/sr)
for which in 'BS':
    y,_=run(which,x); print(('BESURE' if which=='B' else 'Shu87 '),'right-only input -> out L/R rms', np.sqrt(np.mean(y[sr//2:]**2,axis=0)))
# CPU at small buffers
x=np.zeros((sr*10,2)); x[:,0]=0.1*np.random.default_rng(0).standard_normal(sr*10); x[:,1]=x[:,0]
for which in 'BS':
    for b in (32,64,128):
        _,cpu=run(which,x,b); print(('BESURE' if which=='B' else 'Shu87 '),f'block {b:3d}:',cpu.split(': ',1)[1])
