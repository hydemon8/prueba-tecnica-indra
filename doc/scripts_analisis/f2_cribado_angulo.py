# Pose (yaw) estimation screening on INNER validation splits, true class given (isolates pose difficulty)
import sys, numpy as np, warnings
warnings.filterwarnings("ignore")
from scipy.interpolate import CubicSpline
from sklearn.decomposition import PCA
from sklearn.preprocessing import normalize
from sklearn.metrics import roc_auc_score
Z = np.load(sys.argv[1]); A = np.arange(0,360,5).astype(float)
rng = np.random.default_rng(0); s = rng.integers(0,72,100)
def circ(a,b): e=np.abs(a-b)%360; return np.minimum(e,360-e)
def splits():
    yield "A_in", np.tile(A%20==0,(100,1)), np.tile(A%20==10,(100,1))
    yield "C_in", np.tile(A%60==0,(100,1)), np.tile(A%60==30,(100,1))
    tr=np.ones((100,72),bool); va=np.zeros((100,72),bool)
    for i in range(100):
        tr[i,(s[i]+np.arange(12))%72]=False; k=(s[i]+18+np.arange(12))%72; tr[i,k]=False; va[i,k]=True
    yield "B_in", tr, va
# --- mirror-symmetry test of the acquisition geometry (silhouettes)
M = Z["mask"]>0.5; Mf = Z["flip_mask"]>0.5
iou=lambda a,b:(a&b).sum(-1)/np.maximum((a|b).sum(-1),1)
print("silhouette IoU  mask(t) vs flip(mask(t+180)): %.3f | vs mask(t+5): %.3f | vs mask(t+30): %.3f | vs mask(t+90): %.3f" % (
  iou(M, np.roll(Mf,-36,1)).mean(), iou(M,np.roll(M,-1,1)).mean(), iou(M,np.roll(M,-6,1)).mean(), iou(M,np.roll(M,-18,1)).mean()))
def nn_angle(G, ga, Q):            # G gallery feats, ga gallery angles, Q queries -> angle, interp angle, ambiguity ratio
    D = np.linalg.norm(Q[:,None]-G[None],axis=-1)
    o = D.argsort(1); a1 = ga[o[:,0]]; d1 = D[np.arange(len(Q)),o[:,0]]
    # interpolate with the nearest neighbour that is angularly adjacent on the other side
    out=[]; amb=[]
    for q in range(len(Q)):
        far = circ(ga, a1[q])>20
        amb.append(d1[q]/ (D[q,far].min() if far.any() else np.inf))
        cand=[j for j in o[q,1:6] if 0<circ(ga[j],a1[q])<=30]
        if cand:
            j=cand[0]; w1,w2=1/(D[q,o[q,0]]+1e-9),1/(D[q,j]+1e-9)
            v=w1*np.exp(1j*np.deg2rad(a1[q]))+w2*np.exp(1j*np.deg2rad(ga[j])); out.append(np.rad2deg(np.angle(v))%360)
        else: out.append(a1[q])
    return a1, np.array(out), np.array(amb)
def manifold_angle(G, ga, Q, step=0.5):   # periodic cubic spline through gallery points ordered by angle
    o=np.argsort(ga); t=np.r_[ga[o], ga[o][0]+360]; P=np.vstack([G[o],G[o][:1]])
    cs=CubicSpline(t,P,bc_type="periodic"); grid=np.arange(t[0],t[0]+360,step); C=cs(grid)
    D=np.linalg.norm(Q[:,None]-C[None],axis=-1); k=D.argmin(1)
    return grid[k]%360
def report(tag, e): return f"{tag:28s} MAE {e.mean():5.1f}  med {np.median(e):4.1f}  <=10deg {np.mean(e<=10)*100:5.1f}%  >90deg {np.mean(e>90)*100:4.1f}%"
for sname, tr, va in splits():
    print(f"\n== {sname}")
    raw = Z["raw"]; pg = PCA(50, random_state=0).fit(raw[tr])
    banks = {"PCA50 global": pg.transform(raw.reshape(7200,-1)).reshape(100,72,-1),
             "HOG": normalize(Z["hog"].reshape(7200,-1)).reshape(100,72,-1),
             "silhouette": Z["mask"]}
    flipbanks = {"PCA50 global": pg.transform(Z["flip_raw"].reshape(7200,-1)).reshape(100,72,-1),
                 "HOG": normalize(Z["flip_hog"].reshape(7200,-1)).reshape(100,72,-1),
                 "silhouette": Z["flip_mask"]}
    res={}
    for bname, F in list(banks.items()) + [("PCA per-object", None)]:
        e_nn=[];e_in=[];e_mf=[];e_fl=[];amb=[]
        for i in range(100):
            if F is None:
                Xi = Z["raw"][i]; n=tr[i].sum(); p=PCA(min(20,n-1)).fit(Xi[tr[i]]); Fi=p.transform(Xi)
            else: Fi=F[i]
            G,ga,Q,qa = Fi[tr[i]],A[tr[i]],Fi[va[i]],A[va[i]]
            a1,ai,am = nn_angle(G,ga,Q); e_nn+=list(circ(a1,qa)); e_in+=list(circ(ai,qa)); amb+=list(am)
            e_mf+=list(circ(manifold_angle(G,ga,Q),qa))
            if sname=="B_in" and F is not None:
                Gf=np.vstack([G, flipbanks[bname][i][tr[i]]]); gaf=np.r_[ga,(ga+180)%360]
                e_fl+=list(circ(nn_angle(Gf,gaf,Q)[0],qa))
        e_nn,e_in,e_mf,amb=map(np.array,(e_nn,e_in,e_mf,amb))
        print(report(f"{bname} | 1-NN",e_nn)); print(report(f"{bname} | 2-NN interp",e_in)); print(report(f"{bname} | manifold spline",e_mf))
        if e_fl: print(report(f"{bname} | 1-NN + flip(t+180)",np.array(e_fl)))
        bad=e_nn>10
        if 0<bad.sum()<len(bad): print(f"   ambiguity-ratio AUROC for flagging err>10deg: {roc_auc_score(bad, amb):.3f}")
