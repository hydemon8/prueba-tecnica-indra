import sys, numpy as np
from PIL import Image
d,out = sys.argv[1], sys.argv[2]
A=np.arange(0,360,5)
X=np.stack([np.stack([np.asarray(Image.open(f"{d}/obj{o}__{a}.png").convert("RGB")) for a in A]) for o in range(1,101)])
mx=X.max(-1)
for T in (60,80):
    m=mx>T; fg=m.mean((2,3))
    touch=(m[:,:,0,:].any(-1)|m[:,:,-1,:].any(-1)|m[:,:,:,0].any(-1)|m[:,:,:,-1].any(-1))
    print(f"T={T}: fg mean {fg.mean():.3f} min {fg.min():.3f} max {fg.max():.3f} | touch border {touch.sum()} imgs ({touch.mean():.1%}), objs w/ any touch {touch.any(1).sum()}")
# exact duplicate check
h={}
dup=0
for i in range(100):
    for j in range(72):
        k=hash(X[i,j].tobytes()); dup+= k in h; h[k]=1
print("exact duplicate images:", dup)
# brightness per object
print("mean intensity range across objects:", X.mean((1,2,3,4)).min().round(1), X.mean((1,2,3,4)).max().round(1))
# strips for worst-angle objects
objs=[67,65,12,50,47,1,3]
strip=[np.hstack([np.asarray(Image.open(f"{d}/obj{o}__{a}.png").resize((64,64))) for a in range(0,360,30)]) for o in objs]
Image.fromarray(np.vstack(strip)).save(f"{out}/hard_angle_strips.png")
