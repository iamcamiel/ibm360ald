import numpy as np

def local_phases(g,shape):
 xp,yp,x0,y0=[g[k] for k in ['xp','yp','xphase','yphase']]
 good=[]
 for s in g['symbols']:
  x,y,xx,yy=s['box'];ch=s['text'];w=s['word'].strip()
  if len(ch)==1 and ch.isalnum() and s['confidence']>82 and len(w)>=3 and 0.60*yp<yy-y<1.15*yp and xx-x<1.3*xp and y>160:
   good.append(((x+xx)/2,(y+yy)/2))
 values=np.array(good)
 xs=np.arange(250,shape[1]+250,350);ys=np.arange(225,shape[0]+225,400)
 phases=[]
 for axis,pitch,base in [(0,xp,x0),(1,yp,y0)]:
  z=np.exp(2j*np.pi*values[:,axis]/pitch)
  result=np.zeros((len(ys),len(xs)),dtype=complex)
  for r,y in enumerate(ys):
   for c,x in enumerate(xs):
    weights=np.exp(-.5*((values[:,0]-x)/330)**2-.5*((values[:,1]-y)/420)**2)
    result[r,c]=(z*weights).sum()/max(weights.sum(),1e-6)
  angle=np.angle(result)
  angle=np.unwrap(np.unwrap(angle,axis=1 if axis==0 else 0),axis=0 if axis==0 else 1)
  phase=angle*pitch/(2*np.pi)
  # Choose a consistent origin; subsequent phase winding accounts for stretch.
  anchor=phase[1,3]
  phase-=round((anchor-base)/pitch)*pitch
  phases.append(phase)
 def lookup(a,x,y):
  xx=np.clip((x-xs[0])/350,0,len(xs)-1.001);yy=np.clip((y-ys[0])/400,0,len(ys)-1.001)
  c=int(xx);r=int(yy);dx=xx-c;dy=yy-r
  return float((1-dy)*((1-dx)*a[r,c]+dx*a[r,c+1])+dy*((1-dx)*a[r+1,c]+dx*a[r+1,c+1]))
 def col(x,y):return round((x-lookup(phases[0],x,y))/xp)
 def row(x,y):return round((y-lookup(phases[1],x,y))/yp)
 def center(c,r):
  x=x0+c*xp;y=y0+r*yp
  for _ in range(3):x,y=c*xp+lookup(phases[0],x,y),r*yp+lookup(phases[1],x,y)
  return x,y
 return col,row,center,{'x':phases[0].tolist(),'y':phases[1].tolist(),'good_glyphs':len(good)}
