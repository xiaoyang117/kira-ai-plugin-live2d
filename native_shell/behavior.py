"""Pure native interaction math; no Qt or SDK dependencies."""
import math
import uuid


def project_vertices(vertices, matrix, width, height):
    result=[]
    for i in range(0,len(vertices)-1,2):
        x,y=vertices[i:i+2]
        w=matrix[3]*x+matrix[7]*y+matrix[15]
        if abs(w)<1e-8:continue
        result.append(((matrix[0]*x+matrix[4]*y+matrix[12])/w*.5*width+width*.5,
                       height*.5-(matrix[1]*x+matrix[5]*y+matrix[13])/w*.5*height))
    return result


class DragGesture:
    def __init__(self, source, value, minimum, maximum, x, y):
        self.source=source;self.start=float(value);self.value=float(value)
        self.minimum=float(minimum);self.maximum=float(maximum)
        self.x=x;self.y=y;self.gesture=uuid.uuid4().hex;self.boundary=None

    def update(self,x,y,scale=1):
        source=self.source
        delta=(y-self.y) if source.get('axis',0)==1 else (x-self.x)
        factor=source.get('factor',.01)
        if not isinstance(factor,(float,int)) or not math.isfinite(factor):factor=.01
        self.value=max(self.minimum,min(self.maximum,self.start+delta/max(.1,scale)*factor))
        epsilon=max(1e-6,(self.maximum-self.minimum)*.001)
        boundary='min' if self.value<=self.minimum+epsilon else 'max' if self.value>=self.maximum-epsilon else None
        phase=boundary if boundary!=self.boundary else None
        self.boundary=boundary
        return phase

    def packet(self,phase):
        return {'kind':'drag','area':self.source['area'],'parameter':self.source['parameter'],
                'name':self.source['name'],'phase':phase,'gesture':self.gesture,'nonce':uuid.uuid4().hex}


class MouseGaze:
    """Bounded gaze with a small dead zone and frame-rate independent easing."""
    def __init__(self):
        self.x=self.y=0.0

    def step(self, x, y, anchor, radius, delta, enabled=True):
        def direction(offset, distance):
            if abs(offset)<=3:
                return 0.0
            offset-=math.copysign(3,offset)
            return math.tanh(offset/max(1,distance))
        target_x=direction(x-anchor[0],radius[0]) if enabled else 0.0
        target_y=direction(anchor[1]-y,radius[1]) if enabled else 0.0
        weight=-math.expm1(-max(0,min(.1,delta))/.12)
        self.x+=(target_x-self.x)*weight
        self.y+=(target_y-self.y)*weight
        return self.x,self.y
