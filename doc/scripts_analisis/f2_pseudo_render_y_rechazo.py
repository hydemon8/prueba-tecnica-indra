# (1) "pseudo-render": synthesize unseen views from the per-object eigenspace manifold (PCA inverse of spline point)
# (2) risk-coverage of the manifold pose estimator using its own uncertainty (inner splits only)
import sys, numpy as np
from PIL import Image
from scipy.interpolate import CubicSpline
from sklearn.decomposition import PCA
d, out = sys.argv[1], sys.argv[2]
A = np.arange(0,360,5).astype(float)
def circ(a,b): e=np.abs(a-b)%360; return np.minimum(e,360-e)
def load(o): return np.stack([np.asarray(Image.open(f"{d}/obj{o}__{int(a)}.png").convert("RGB"),np.float32)/255 for a in A])
rows=[]; errs=[]
for o in [5, 19, 65, 82, 1]:
    X = load(o).reshape(72,-1); tr = A%20==0          # learn from 18 views (every 20deg)
    p = PCA(17).fit(X[tr]); C = p.transform(X[tr])
    cs = CubicSpline(np.r_[A[tr],360], np.vstack([C,C[:1]]), bc_type="periodic")
    row=[]
    for a in [10, 50, 130, 250]:                      # all unseen angles
        gt = X[A==a][0]; nn = X[tr][np.argmin(circ(A[tr],a))]
        syn = np.clip(p.inverse_transform(cs([a]))[0],0,1)
        errs.append((np.abs(syn-gt).mean(), np.abs(nn-gt).mean()))
        row += [gt, nn, syn]
    rows.append(np.hstack([r.reshape(128,128,3) for r in row]))
Image.fromarray((np.vstack(rows)*255).astype(np.uint8)).resize((12*80, 5*80)).save(f"{out}/pseudo_render.png")
e=np.array(errs); print(f"pixel MAE vs ground truth: manifold-render {e[:,0].mean():.4f} | nearest seen view {e[:,1].mean():.4f}")
# ---- risk-coverage (global PCA50 manifold, true class) with uncertainty = d_min * ambiguity
Z = np.load(f"{out}/feats.npz"); raw = Z["raw"]
rng=np.random.default_rng(0); s=rng.integers(0,72,100)
def run(tr, va, name):
    pg=PCA(50,random_state=0).fit(raw[tr]); F=pg.transform(raw.reshape(7200,-1)).reshape(100,72,-1)
    E=[];U=[]
    for i in range(100):
        G,ga=F[i][tr[i]],A[tr[i]]; o=np.argsort(ga)
        cs=CubicSpline(np.r_[ga[o],ga[o][0]+360],np.vstack([G[o],G[o][:1]]),bc_type="periodic")
        grid=np.arange(ga[o][0],ga[o][0]+360,0.5); Cg=cs(grid)
        for q,qa in zip(F[i][va[i]],A[va[i]]):
            dd=np.linalg.norm(Cg-q,axis=1); k=dd.argmin(); th=grid[k]%360
            far=circ(grid%360,th)>20; amb=dd[k]/dd[far].min()
            gap=np.min(circ(ga,th))                      # distance to nearest *observed* view
            E.append(circ(th,qa)); U.append(amb + gap/30)  # simple heuristic score, not tuned
    E,U=np.array(E),np.array(U); o=np.argsort(U)
    msg=[]
    for cov in (1.0,0.8,0.6,0.4):
        n=int(len(o)*cov); msg.append(f"cov {cov:.0%}: {np.mean(E[o[:n]]<=10)*100:5.1f}%")
    print(f"{name:6s} within +-10deg among accepted ->  " + " | ".join(msg))
run(np.tile(A%20==0,(100,1)), np.tile(A%20==10,(100,1)), "A_in")
run(np.tile(A%60==0,(100,1)), np.tile(A%60==30,(100,1)), "C_in")
tr=np.ones((100,72),bool); va=np.zeros((100,72),bool)
for i in range(100):
    tr[i,(s[i]+np.arange(12))%72]=False; k=(s[i]+18+np.arange(12))%72; tr[i,k]=False; va[i,k]=True
run(tr,va,"B_in")
