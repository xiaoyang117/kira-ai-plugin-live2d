"""Apply authored part-opacity tracks that the native motion player misses."""
import json
from pathlib import Path


def curve_value(segments, moment):
    time, value = segments[:2]
    index = 2
    while index < len(segments):
        kind = segments[index]
        if kind == 1:
            x1, y1, x2, y2, end, final = segments[index+1:index+7]
            if moment <= end:
                # Cubism uses time as the Bezier X coordinate, not its fraction.
                low, high = 0., 1.
                for _ in range(24):
                    u = (low+high)/2
                    x = (1-u)**3*time+3*(1-u)**2*u*x1+3*(1-u)*u*u*x2+u**3*end
                    if x < moment:low = u
                    else:high = u
                u = (low+high)/2
                return (1-u)**3*value+3*(1-u)**2*u*y1+3*(1-u)*u*u*y2+u**3*final
            index += 7
        else:
            end, final = segments[index+1:index+3]
            if moment < end:
                if kind == 2:return value
                if kind == 3:return final
                return value+(final-value)*max(0.,min(1.,(moment-time)/max(1e-12,end-time)))
            index += 3
        time, value = end, final
    return value


class PartMotion:
    def __init__(self, ids, initial=None):
        self.indices = {ident:index for index,ident in enumerate(ids)}
        self.values = dict(initial or {})
        self.cache = {}
        self.active = [];self.elapsed = 0.;self.duration = 0.;self.loop = False

    def start(self, path):
        key = str(path)
        if key not in self.cache:
            data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            curves = [c for c in data.get('Curves',[]) if c.get('Target')=='PartOpacity' and c.get('Id') in self.indices]
            self.cache[key] = (curves,float(data.get('Meta',{}).get('Duration',0)),bool(data.get('Meta',{}).get('Loop',False)))
        self.active,self.duration,self.loop = self.cache[key]
        self.elapsed = 0.
        # Parts are discrete alternatives in many models. Apply initial values
        # immediately rather than cross-fading two incompatible hand meshes.
        self.advance(0.)

    def advance(self, delta):
        self.elapsed += max(0.,delta)
        moment = self.elapsed
        if self.loop and self.duration>0:moment %= self.duration
        for curve in self.active:
            self.values[curve['Id']] = max(0.,min(1.,curve_value(curve['Segments'],moment)))
        if not self.loop and self.elapsed>=self.duration:self.active = []

    def apply(self, model):
        for ident,value in self.values.items():
            if ident in self.indices:model.SetPartOpacity(self.indices[ident],value)
