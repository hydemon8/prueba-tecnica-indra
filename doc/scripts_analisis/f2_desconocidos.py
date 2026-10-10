# Inner open-set check: outer-D unknowns removed; 10 *other* objects act as inner unknowns
import sys, numpy as np
from sklearn.preprocessing import normalize
from sklearn.metrics import roc_auc_score
from sklearn.decomposition import PCA
Z=np.load(sys.argv[1]); A=np.arange(0,360,5)
rng=np.random.default_rng(1); outer_unk=rng.choice(100,10,replace=False)
pool=np.setdiff1d(np.arange(100),outer_unk)
scen={"random":rng.choice(pool,10,replace=False)}
twins=[t-1 for t in (3,15,23,75,80,64,83,85,22,65) if t-1 in pool]   # one member of visually confusable pairs (1-based ids)
scen["twins (adversarial)"]=np.array(twins[:10])
tr=A%20==0; va=A%20==10
for sname,unk in scen.items():
    kn=np.setdiff1d(pool,unk)
    for fname,F in [("PCA50 raw",None),("HSV",normalize(Z["hsv"].reshape(7200,-1)).reshape(100,72,-1)),
                    ("HOG",normalize(Z["hog"].reshape(7200,-1)).reshape(100,72,-1)),
                    ("HSV+HOG",np.concatenate([normalize(Z[k].reshape(7200,-1)) for k in ("hsv","hog")],1).reshape(100,72,-1))]:
        if F is None:
            p=PCA(50,random_state=0).fit(Z["raw"][kn][:,tr].reshape(-1,3072)); F=p.transform(Z["raw"].reshape(7200,-1)).reshape(100,72,-1)
        G=F[kn][:,tr].reshape(-1,F.shape[-1]); qk=F[kn][:,va].reshape(-1,F.shape[-1]); qu=F[unk].reshape(-1,F.shape[-1])
        d2=lambda Q:np.sqrt(np.maximum((Q**2).sum(1)[:,None]+(G**2).sum(1)[None]-2*Q@G.T,0)).min(1); dk=d2(qk); du=d2(qu)
        auc=roc_auc_score(np.r_[np.zeros(len(dk)),np.ones(len(du))],np.r_[dk,du]); thr=np.percentile(dk,95)
        print(f"{sname:20s} {fname:10s} AUROC {auc:.3f} | unknown accepted at 95% known-recall: {np.mean(du<=thr)*100:5.1f}%")
