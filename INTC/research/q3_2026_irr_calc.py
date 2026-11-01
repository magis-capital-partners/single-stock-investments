"""AMZN and INTC Q3 2026 update: 7-yr owner-cash IRR (house convention, see compounders/irr_2026-10-29/core_irr.py).
CF0=-price; CF1..6 = owner cash/sh; CF7 = OC7 x (1+exit). Inputs: Q3-26 8-K releases (2026-10-29); prices = 2026-10-29 regular-session close (Yahoo/yfinance; Reuters & StockTitan agree).
Growth, capex normalization, margins and exit multiples are ASSUMPTIONS."""
def irr(p,f):
    lo,hi=-0.99,1.0
    for _ in range(300):
        m=(lo+hi)/2; npv=-p+sum(x/(1+m)**(i+1) for i,x in enumerate(f))
        lo,hi=(m,hi) if npv>0 else (lo,m)
    return m
def pv(f,r=.15): return sum(x/(1+r)**(i+1) for i,x in enumerate(f))
def grow(oc,g1,g2,exit):
    out,x=[],oc
    for t in range(1,8):
        x*=1+(g1 if t<=5 else g2); out.append(x)
    return out[:6]+[out[6]*(1+exit)], out
# ---------- AMZN ----------
P=243.79; SH=10.929  # diluted wtd Q3-26, bn
REV=797.455; OCF=168.300; SBC=19.873; CAPEX=210.657; DA=79.353; OI=104.366
print('AMZN TTM actual owner cash/sh', round((OCF-CAPEX-SBC)/SH,2))
oc12=(OCF-SBC-0.12*REV)/SH; oc15=(OCF-SBC-0.15*REV)/SH; nopat=OI*(1-0.20)/SH
A={'bear':dict(oc=oc15,g1=.10,g2=.07,exit=20,note='capex normalized at 15% of TTM revenue'),
   'base':dict(oc=oc12,g1=.13,g2=.09,exit=25,note='capex normalized at 12% of TTM revenue (house method)'),
   'bull':dict(oc=nopat,g1=.16,g2=.10,exit=25,note='owner earnings = TTM operating income x (1-20% tax); maintenance capex = D&A')}
for k,d in A.items():
    f,path=grow(d['oc'],d['g1'],d['g2'],d['exit'])
    print('AMZN',k,'OC0 %.2f'%d['oc'],'OC7 %.2f'%path[6],'IRR %.1f%%'%(irr(P,f)*100),'15%% price %.0f'%pv(f),d['note'])
# ---------- INTC ----------
P=92.07; SH0=5.310
REV0=59.892  # TTM Q4-25..Q3-26
# explicit owner-cash margin paths (OCF - gross capex - SBC, % revenue), revenue growth, dilution, exit
I={'bear':dict(g=.03,m=[-.08,-.06,-.03,0,.02,.03,.04],dil=.02,exit=15),
   'base':dict(g=.07,m=[-.08,-.04,0,.04,.07,.10,.12],dil=.01,exit=20),
   'bull':dict(g=.12,m=[-.04,0,.06,.12,.16,.19,.22],dil=0,exit=22)}
for k,d in I.items():
    f=[];rev=REV0;sh=SH0
    for t in range(7):
        rev*=1+d['g']; sh*=1+d['dil']; f.append(rev*d['m'][t]/sh)
    oc7=f[-1]; f[-1]=oc7*(1+d['exit'])
    print('INTC',k,'rev7 %.0f'%rev,'OC7/sh %.2f'%oc7,'IRR %.1f%%'%(irr(P,f)*100),'15%% price %.1f'%pv(f), 'flows',[round(x,2) for x in f])
print('INTC TTM owner cash/sh', round((17.472-13.704-2.432)/SH0,2))
