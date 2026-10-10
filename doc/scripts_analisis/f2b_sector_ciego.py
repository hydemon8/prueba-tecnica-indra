# Blind-sector (inner B) pose: spline vs Fourier periodic regression vs mirror-symmetry gap filling. True class given.
import sys, numpy as np, warnings
warnings.filterwarnings("ignore")
from scipy.interpolate import CubicSpline
from sklearn.decomposition import PCA
Z=np.load(sys.argv[1]); A=np.arange(0,360,5).astype(float)
def circ(a,b): e=np.abs(a-b)%360; return np.minimum(e,360-e)
rng=np.random.default_rng(0); s=rng.integers(0,72,100)
tr=np.ones((100,72),bool); va=np.zeros((100,72),bool)
for i in range(100):
    tr[i,(s[i]+np.arange(12))%72]=False; k=(s[i]+18+np.arange(12))%72; tr[i,k]=False; va[i,k]=True
p=PCA(50,random_state=0).fit(Z["raw"][tr])
F=p.transform(Z["raw"].reshape(7200,-1)).reshape(100,72,-1); Ff=p.transform(Z["flip_raw"].reshape(7200,-1)).reshape(100,72,-1)
grid=np.arange(0,360,0.5)
def spline_curve(G,ga):
    o=np.argsort(ga); cs=CubicSpline(np.r_[ga[o],ga[o][0]+360],np.vstack([G[o],G[o][:1]]),bc_type="periodic")
    return cs(np.where(grid<ga[o][0],grid+360,grid))
def fourier_curve(G,ga,K,lam=1e-3):
    B=lambda t: np.column_stack([np.ones_like(t)]+[f(k*np.deg2rad(t)) for k in range(1,K+1) for f in (np.cos,np.sin)])
    X=B(ga); W=np.linalg.solve(X.T@X+lam*np.eye(X.shape[1]),X.T@G); return B(grid)@W
def est(C,Q): return grid[np.argmin(((Q[:,None]-C[None])**2).sum(-1),1)]
def mirror_axis(G,Gf,ga):
    """find vertical mirror plane alpha s.t. I(theta) ~ flip(I(2alpha-theta)); score normalised by 5deg-neighbour distance"""
    idx={a:j for j,a in enumerate(ga)}
    d5=np.median([np.linalg.norm(G[idx[a]]-G[idx[(a+5)%360]]) for a in ga if (a+5)%360 in idx])
    best=(np.inf,None)
    for al in np.arange(0,180,2.5):
        pr=[(idx[a],idx[(2*al-a)%360]) for a in ga if (2*al-a)%360 in idx]
        if len(pr)<8: continue
        sc=np.median([np.linalg.norm(G[x]-Gf[y]) for x,y in pr])/d5
        best=min(best,(sc,al))
    return best
res={k:[] for k in ["spline","fourier K=4","fourier K=8","spline+mirror fill"]}; sym=[]; per_obj=[]
for i in range(100):
    G,ga,Q,qa=F[i][tr[i]],A[tr[i]],F[i][va[i]],A[va[i]]
    res["spline"]+=list(circ(est(spline_curve(G,ga),Q),qa))
    res["fourier K=4"]+=list(circ(est(fourier_curve(G,ga,4),Q),qa))
    res["fourier K=8"]+=list(circ(est(fourier_curve(G,ga,8),Q),qa))
    sc,al=mirror_axis(G,Ff[i][tr[i]],ga); sym.append(sc)
    G2,ga2=G,ga
    if sc<2.0:   # mirror-consistent object: synthesise missing angles from flipped observed views
        new=(2*al-ga)%360; m=~np.isin(new,ga)
        G2=np.vstack([G,Ff[i][tr[i]][m]]); ga2=np.r_[ga,new[m]]
    e=circ(est(spline_curve(G2,ga2),Q),qa); res["spline+mirror fill"]+=list(e)
    per_obj.append((sc, np.mean(circ(est(spline_curve(G,ga),Q),qa)<=10), np.mean(e<=10)))
for k,v in res.items():
    v=np.array(v); print(f"B_in {k:20s} <=10deg {np.mean(v<=10)*100:5.1f}%  MAE {v.mean():5.1f}  med {np.median(v):5.1f}  >90deg {np.mean(v>90)*100:4.1f}%")
po=np.array(per_obj); m=po[:,0]<2.0
print(f"mirror-consistent objects (score<2): {m.sum()}/100 | on them: spline {po[m,1].mean()*100:.1f}% -> +mirror {po[m,2].mean()*100:.1f}% within 10deg")
print("mirror score quantiles:", np.round(np.quantile(po[:,0],[0.1,0.25,0.5,0.75,0.9]),2))
# --- deterministic coverage rule: act only if the estimated angle lies within `r` deg of an observed reference view
print("\ncoverage rule on B_in (spline estimate):")
for r in (5,7.5,10):
    acc=[];unsafe=[];cov=[]
    for i in range(100):
        G,ga,Q,qa=F[i][tr[i]],A[tr[i]],F[i][va[i]],A[va[i]]
        th=est(spline_curve(G,ga),Q); e=circ(th,qa); ok=np.array([circ(ga,t).min()<=r for t in th])
        cov+=list(ok); unsafe+=list(ok&(e>10)); acc+=list(e[ok]<=10)
    print(f"  r={r:4.1f}: acts on {np.mean(cov)*100:5.1f}% | within 10deg among acted {np.mean(acc)*100:5.1f}% | unsafe actions {np.mean(unsafe)*100:4.1f}% of all")
# --- gap-aware rule: SKU coverage map is known; reject if the estimate falls inside a gap or within delta of its edges
print("\ngap-aware rule on B_in (all queries truly inside a blind arc):")
for dl in (0,10,15,20):
    unsafe=[];acted=[]
    for i in range(100):
        G,ga,Q,qa=F[i][tr[i]],A[tr[i]],F[i][va[i]],A[va[i]]
        th=est(spline_curve(G,ga),Q); e=circ(th,qa)
        missing=A[~tr[i]]                                  # angles with no reference view (the gaps)
        near=np.array([circ(missing,t).min()<=dl+2.5 for t in th])
        acted+=list(~near); unsafe+=list((~near)&(e>10))
    cov_lost=min(1, 4*dl/240)                              # share of the covered circle also blocked (2 gaps x 2 edges)
    print(f"  delta={dl:2d}: robot acts on {np.mean(acted)*100:5.1f}% of blind queries | unsafe {np.mean(unsafe)*100:4.1f}% | covered-circle also blocked ~{cov_lost*100:4.1f}%")
# --- active vision: rotate the object by a known delta and capture again; the 2nd view's own reference image is
#     removed from the gallery (leave-one-out) so the 2nd shot is a genuinely unseen image
print("\ntwo-shot (rotate by known delta, re-capture) on B_in:")
for D in (90,180):
    e2=[];agree=[]
    for i in range(100):
        G,ga=F[i][tr[i]],A[tr[i]]
        for j in np.where(va[i])[0]:
            t2=(A[j]+D)%360; j2=int(t2//5)
            keep=ga!=t2; C=spline_curve(G[keep],ga[keep])
            th2=est(C,F[i][j2][None])[0]; th=(th2-D)%360
            th1=est(spline_curve(G,ga),F[i][j][None])[0]
            e2.append(circ(th,A[j])); agree.append(circ(th1,th)<=15)
    e2=np.array(e2); agree=np.array(agree)
    print(f"  delta={D}: angle from 2nd shot within 10deg {np.mean(e2<=10)*100:5.1f}% (MAE {e2.mean():.1f}) | shots agree on {agree.mean()*100:.1f}%")
