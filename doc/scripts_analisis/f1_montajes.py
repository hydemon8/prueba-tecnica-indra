import sys, numpy as np
from PIL import Image
d, out = sys.argv[1], sys.argv[2]
# grid of all 100 objects at 0 deg, 64px thumbnails
tiles=[np.asarray(Image.open(f"{d}/obj{i}__0.png").resize((64,64))) for i in range(1,101)]
rows=[np.hstack(tiles[r*10:(r+1)*10]) for r in range(10)]
Image.fromarray(np.vstack(rows)).save(f"{out}/all_objects_0deg.png")
# rotation strip for a few objects
objs=[1,3,5,13,19,47,65,82]
strip=[np.hstack([np.asarray(Image.open(f"{d}/obj{o}__{a}.png").resize((64,64))) for a in range(0,360,30)]) for o in objs]
Image.fromarray(np.vstack(strip)).save(f"{out}/rotation_strips.png")
