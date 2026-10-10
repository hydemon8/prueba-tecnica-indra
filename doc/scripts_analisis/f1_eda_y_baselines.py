import sys, numpy as np
from PIL import Image
d = sys.argv[1]
O, A = np.arange(1,101), np.arange(0,360,5)
X = np.zeros((100,72,128,128,3), np.uint8)
for i,o in enumerate(O):
    for j,a in enumerate(A):
        X[i,j] = np.asarray(Image.open(f"{d}/obj{o}__{a}.png").convert("RGB"))
print("shape", X.shape)
# --- background / foreground
corners = np.concatenate([X[:,:,:8,:8].reshape(-1,3), X[:,:,:8,-8:].reshape(-1,3)])
print("corner px mean/std/p99:", corners.mean(0).round(1), corners.std(0).round(1), np.percentile(corners.max(1),99))
mx = X.max(-1)
fg = (mx > 40).mean((2,3))  # foreground fraction per image
print("fg frac: mean %.3f min %.3f max %.3f" % (fg.mean(), fg.min(), fg.max()))
cv = fg.std(1)/fg.mean(1)
print("per-object fg-area CV across angles: median %.2f max %.2f (obj %d)" % (np.median(cv), cv.max(), O[cv.argmax()]))
# bbox touches border?
touch = ((mx[:,:,0,:]>40).any(-1)|(mx[:,:,-1,:]>40).any(-1)|(mx[:,:,:,0]>40).any(-1)|(mx[:,:,:,-1]>40).any(-1))
print("images whose object touches border: %d" % touch.sum())
# --- features: 32x32 rgb downsample, L2-normalized
small = X.reshape(100,72,32,4,32,4,3).mean((3,5)).reshape(100,72,-1).astype(np.float32)
small -= small.mean(-1, keepdims=True); small /= np.linalg.norm(small,axis=-1,keepdims=True)
def hsv_hist(img):
    im = Image.fromarray(img).convert("HSV"); h = np.asarray(im)
    m = img.max(-1) > 40
    H,_ = np.histogramdd(h[m][:, :3], bins=(16,4,4), range=((0,256),(0,256),(0,256)))
    H = H.ravel()+1e-6; return np.sqrt(H/H.sum())
hist = np.array([[hsv_hist(X[i,j]) for j in range(72)] for i in range(100)], np.float32)
def circ(a,b): e=np.abs(a-b)%360; return np.minimum(e,360-e)
def run(name, tr_mask, te_mask, feat, objs=None):
    objs = np.arange(100) if objs is None else objs
    Ftr = feat[objs][:, tr_mask]; Fte = feat[objs][:, te_mask]
    ytr = np.repeat(objs, tr_mask.sum()); atr = np.tile(A[tr_mask], len(objs))
    yte = np.repeat(objs, te_mask.sum()); ate = np.tile(A[te_mask], len(objs))
    Ftr = Ftr.reshape(len(ytr),-1); Fte = Fte.reshape(len(yte),-1)
    D = 2-2*Fte@Ftr.T
    nn = D.argmin(1); yp = ytr[nn]; acc = (yp==yte).mean()
    # angle: NN restricted to true class (isolates pose difficulty)
    Dc = np.where(ytr[None,:]==yte[:,None], D, np.inf); ap = atr[Dc.argmin(1)]
    e = circ(ap, ate)
    return acc, e, yte, yp, D
res = {}
odd = A%10==5
for fname, F in [("raw32", small), ("hsvhist", hist)]:
    acc,e,yte,yp,_ = run("A", ~odd, odd, F)
    print(f"[A {fname}] 1NN acc={acc:.4f} | angle(true cls) MAE={e.mean():.1f} med={np.median(e):.1f} <=10deg={np.mean(e<=10):.3f} >90deg={np.mean(e>90):.3f}")
    res[("A",fname)] = (e,yte)
    c = A%30==0
    acc,e,yte,yp,_ = run("C", c, ~c, F)
    print(f"[C {fname}] 1NN acc={acc:.4f} | angle MAE={e.mean():.1f} med={np.median(e):.1f} <=10deg={np.mean(e<=10):.3f} >90deg={np.mean(e>90):.3f}")
    res[("C",fname)] = (e,yte,yp)
# protocol B: per-object random arc of 60deg (12 views) - simulate with per-object masks
rng = np.random.default_rng(0)
starts = rng.integers(0,72,100)
eB=[]; okB=0; n=0
Ftr_all=[];ytr=[];atr=[]; tests=[]
for i in range(100):
    m = np.zeros(72,bool); m[(starts[i]+np.arange(12))%72]=True
    Ftr_all.append(small[i,~m]); ytr += [i]*60; atr += list(A[~m]); tests.append((i,m))
Ftr_all=np.concatenate(Ftr_all); ytr=np.array(ytr); atr=np.array(atr)
for i,m in tests:
    Fte=small[i,m]; D=2-2*Fte@Ftr_all.T
    okB += (ytr[D.argmin(1)]==i).sum(); n+=m.sum()
    Dc=np.where(ytr[None,:]==i,D,np.inf); eB += list(circ(atr[Dc.argmin(1)],A[m]))
eB=np.array(eB)
print(f"[B raw32] 1NN acc={okB/n:.4f} | angle MAE={eB.mean():.1f} med={np.median(eB):.1f} <=10deg={np.mean(eB<=10):.3f} >90deg={np.mean(eB>90):.3f}")
# theoretical floor in B if predicting nearest seen angle: arc offsets 0..55 -> distance to nearest edge view
off=np.arange(12)*5; floor=np.minimum(off+5, 60-off)
print("  B oracle-nearest-seen-angle floor: <=10deg frac=%.3f, mean=%.1f" % (np.mean(floor<=10), floor.mean()))
# per-object angle difficulty (protocol A raw32)
e,yte = res[("A","raw32")]
per = np.array([e[yte==i].mean() for i in range(100)])
flip = np.array([np.mean((e[yte==i]>150)) for i in range(100)])
order = per.argsort()[::-1]
print("worst-angle objects (A, raw32): ", [(int(O[i]), round(float(per[i]),1), round(float(flip[i]),2)) for i in order[:15]])
print("objects with angle MAE>20 in A:", int((per>20).sum()), " MAE<=5:", int((per<=5).sum()))
# self-similarity profile: distance vs delta-angle, normalized
dprof = np.zeros((100,37))
for i in range(100):
    G = 2-2*small[i]@small[i].T
    for k in range(37):
        dprof[i,k] = np.mean([G[j,(j+k)%72] for j in range(72)])
ratio180 = dprof[:,36]/dprof[:,18]   # d(180)/d(90): <1 => 2-fold-ish symmetry
flat = dprof[:,1:].max(1)/ (dprof[:,1]+1e-9)  # how much appearance changes with rotation vs 5deg step
print("2-fold symmetric candidates d180/d90<0.6:", [int(O[i]) for i in np.where(ratio180<0.6)[0]])
print("near rotation-invariant (max d / d5 < 3):", [int(O[i]) for i in np.where(flat<3)[0]])
# inter-class confusion (C raw32)
e,yte,yp = res[("C","raw32")]
from collections import Counter
conf = Counter((int(O[a]),int(O[b])) for a,b in zip(yte,yp) if a!=b)
print("top confusions C raw32 (true,pred):", conf.most_common(10))
# protocol D: open set with 1NN distance as unknown score (raw32, all angles of 90 known as gallery, test: unknown objs all views vs known held-out odd views)
unk = rng.choice(100,10,replace=False); kn = np.setdiff1d(np.arange(100),unk)
gal = small[kn][:,~odd].reshape(-1,small.shape[-1]); gy=np.repeat(kn,36)
qk = small[kn][:,odd].reshape(-1,small.shape[-1]); qu = small[unk].reshape(-1,small.shape[-1])
sk = (2-2*qk@gal.T).min(1); su=(2-2*qu@gal.T).min(1)
from sklearn.metrics import roc_auc_score
auc = roc_auc_score(np.r_[np.zeros(len(sk)),np.ones(len(su))], np.r_[sk,su])
thr = np.percentile(sk,95); fpr = np.mean(su<=thr)
print(f"[D raw32] unknown objs={sorted(O[unk].tolist())} AUROC(1NN dist)={auc:.3f}  unknown accepted @95%TPR-known={fpr:.3f}")
