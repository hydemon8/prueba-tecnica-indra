# Classification screening on INNER validation splits only (outer test views never touched)
import sys, time, numpy as np, warnings
warnings.filterwarnings("ignore")
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler, normalize
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC, LinearSVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
Z = np.load(sys.argv[1]); A = np.arange(0,360,5)
rng = np.random.default_rng(0); s = rng.integers(0,72,100)   # outer-B arc starts (fixed seed)
def splits():
    yield "A_in (tr 0mod20 / val 10mod20)", np.tile(A%20==0,(100,1)), np.tile(A%20==10,(100,1))
    yield "C_in (tr 0mod60 / val 30mod60)", np.tile(A%60==0,(100,1)), np.tile(A%60==30,(100,1))
    tr = np.ones((100,72),bool); va = np.zeros((100,72),bool)
    for i in range(100):
        tr[i,(s[i]+np.arange(12))%72] = False                 # outer test arc: excluded
        k = (s[i]+18+np.arange(12))%72; tr[i,k]=False; va[i,k]=True   # inner blind arc at +90deg
    yield "B_in (inner 60deg blind arc)", tr, va
def blocks(names):
    return np.concatenate([normalize(Z[n].reshape(7200,-1)) for n in names], 1).reshape(100,72,-1)
feats = {
  "PCA50(raw32)": None, "HSV": blocks(["hsv"]), "HOG": blocks(["hog"]), "LBP": blocks(["lbp"]),
  "HSV+HOG+LBP": blocks(["hsv","hog","lbp"]),
}
clfs = {
  "1NN": lambda: KNeighborsClassifier(1, metric="cosine"),
  "LogReg": lambda: LogisticRegression(C=10, max_iter=300),
  "LinSVM": lambda: LinearSVC(C=1),
  "SVM-RBF": lambda: SVC(C=10, gamma="scale"),
  "RF500": lambda: RandomForestClassifier(500, n_jobs=3, random_state=0),
}
y = np.repeat(np.arange(100),72).reshape(100,72)
only=sys.argv[2]
for sname, tr, va in splits():
    if not sname.startswith(only): continue
    print(f"\n== {sname}: train {tr.sum()} / val {va.sum()}")
    print(f"{'feature':14s}" + "".join(f"{c:>10s}" for c in clfs) + "   ms/img(best)")
    for fname, F in feats.items():
        if F is None:   # PCA fit on train views only
            raw = Z["raw"]; p = PCA(50, random_state=0).fit(raw[tr]); F = p.transform(raw.reshape(7200,-1)).reshape(100,72,-1)
        Xtr, Xva = F[tr], F[va]; ytr, yva = y[tr], y[va]
        if Xtr.shape[1] > 150:
            pr = PCA(150, random_state=0).fit(Xtr); Xtr, Xva = pr.transform(Xtr), pr.transform(Xva)
        sc = StandardScaler().fit(Xtr); Xtr_s, Xva_s = sc.transform(Xtr), sc.transform(Xva)
        row=[]; best=(0,0)
        for cname, mk in clfs.items():
            m = mk(); a,b = (Xtr, Xva) if cname=="1NN" else (Xtr_s, Xva_s)
            m.fit(a, ytr); t=time.perf_counter(); acc = (m.predict(b)==yva).mean(); dt=(time.perf_counter()-t)/len(yva)*1000
            row.append(acc); best = max(best,(acc,dt))
        print(f"{fname:14s}" + "".join(f"{r*100:9.2f}%" for r in row) + f"   {best[1]:.3f}")
