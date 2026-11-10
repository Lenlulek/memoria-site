import sys, math, random
sys.path.insert(0,'/mnt/project-files/flyers-memoria/_source')
from handdraw import pomegranate_svg, aril_paths
def seeds(W,H,centers,seed=1,stroke=.18,dens=1.2):
    rnd=random.Random(seed); pts=[]
    def near(x,y):
        best,bc=0,None
        for c in centers:
            cx,cy,r=c; d=math.exp(-((x-cx)**2+(y-cy)**2)/(2*r*r))
            if d>best: best,bc=d,c
        return best,bc
    for _ in range(int(W*H*dens)):
        x,y=rnd.uniform(-4,W+4),rnd.uniform(-4,H+4); d,c=near(x,y)
        if rnd.random()>d**1.6: continue
        sz=rnd.uniform(1.4,2.1)*(0.75+0.45*d)
        if all((x-px)**2+(y-py)**2>(sz+ps+.6)**2 for px,py,ps,_ in pts):
            a=math.degrees(math.atan2(c[1]-y,c[0]-x))+90+rnd.uniform(-35,35); pts.append((x,y,sz,a))
    d=" ".join(" ".join(aril_paths(x,y,q,a,rnd,w=stroke*1.3)) for x,y,q,a in pts)
    return f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><path d="{d}" fill="currentColor"/></svg>'
out={
 'SEEDS_HERO': seeds(120,70,[(0,70,13),(120,0,11)],seed=3),
 'SEEDS_STRIP': seeds(160,14,[(160,7,9),(0,7,6)],seed=5),
 'SEEDS_ABOUT': seeds(100,80,[(100,80,14),(100,0,8)],seed=7),
 'SEEDS_FOOT': seeds(160,30,[(0,30,12),(160,0,9)],seed=11),
 'POM': pomegranate_svg('currentColor',weight=1.1).replace('<svg ','<svg aria-hidden="true" '),
}
import json; json.dump(out,open('orn.json','w'))
for k,v in out.items(): print(k,len(v))
