# Precompute feature banks for all 7200 images (+ horizontally flipped copies) -> npz cache
import sys, numpy as np, time
from PIL import Image
from skimage.feature import hog, local_binary_pattern
d, out = sys.argv[1], sys.argv[2]
A = np.arange(0,360,5)
X = np.stack([np.stack([np.asarray(Image.open(f"{d}/obj{o}__{a}.png").convert("RGB")) for a in A]) for o in range(1,101)])
def feats(img):
    g = np.asarray(Image.fromarray(img).convert("L"), np.float32)
    raw = np.asarray(Image.fromarray(img).resize((32,32), Image.BILINEAR), np.float32).ravel()
    h = np.asarray(Image.fromarray(img).convert("HSV")); m = img.max(-1) > 60
    H,_ = np.histogramdd(h[m][:, :3], bins=(16,4,4), range=((0,256),)*3); H = np.sqrt(H.ravel()/max(H.sum(),1))
    g64 = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((64,64), Image.BILINEAR), np.float32)
    ho = hog(g64, orientations=9, pixels_per_cell=(8,8), cells_per_block=(2,2), feature_vector=True)
    l1 = np.bincount(local_binary_pattern(g, 8, 1, "uniform").astype(int).ravel(), minlength=10)
    l2 = np.bincount(local_binary_pattern(g, 16, 2, "uniform").astype(int).ravel(), minlength=18)
    lbp = np.r_[l1/l1.sum(), l2/l2.sum()]
    mask = np.asarray(Image.fromarray((m*255).astype(np.uint8)).resize((32,32), Image.BILINEAR), np.float32).ravel()/255
    return raw, H, ho, lbp, mask
t=time.time()
F = {k: [] for k in ["raw","hsv","hog","lbp","mask"]}
Ff = {k: [] for k in F}
for i in range(100):
    for j in range(72):
        for bank, img in ((F, X[i,j]), (Ff, X[i,j][:, ::-1].copy())):
            for k, v in zip(bank, feats(img)): bank[k].append(v)
el = (time.time()-t)/(7200*2)
np.savez_compressed(f"{out}/feats.npz", **{k: np.array(v, np.float32).reshape(100,72,-1) for k,v in F.items()},
                    **{"flip_"+k: np.array(v, np.float32).reshape(100,72,-1) for k,v in Ff.items()})
print(f"feature extraction {el*1000:.1f} ms/img; dims:", {k: len(v[0]) for k,v in F.items()})
