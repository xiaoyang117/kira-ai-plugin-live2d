"""Recover authored startup part visibility without running viewer commands."""
import math
from pathlib import Path
from ..model_profile import read_json


def initial_part_opacities(source, data=None):
    source=Path(source).resolve()
    data=read_json(source) if data is None else data
    refs=data.get('FileReferences',{})
    if not isinstance(refs,dict) or refs.get('Pose'):return {}
    groups=refs.get('Motions')
    if not isinstance(groups,dict):return {}
    root=next((key for key in groups if key.casefold() in ('idle','standby')),None)
    if root is None:return {}
    result={};seen=set()
    def visit(group,name='',depth=0):
        key=(group,name)
        if depth>8 or key in seen or len(seen)>=64:return
        seen.add(key)
        rows=groups.get(group,[])
        if not isinstance(rows,list):return
        row=next((r for r in rows if isinstance(r,dict) and (not name or r.get('Name')==name)),None)
        if row is None:return
        filename=row.get('File')
        if isinstance(filename,str) and filename:
            file=(source.parent/filename).resolve()
            if file.is_relative_to(source.parent) and file.is_file():
                try:motion=read_json(file)
                except (ValueError,OSError):motion={}
                for curve in motion.get('Curves',[]) if isinstance(motion.get('Curves'),list) else []:
                    if not isinstance(curve,dict) or curve.get('Target')!='PartOpacity':continue
                    ident,segments=curve.get('Id'),curve.get('Segments')
                    if (isinstance(ident,str) and ident and isinstance(segments,list) and len(segments)>=2
                            and type(segments[1]) in (int,float) and math.isfinite(segments[1])):
                        result.setdefault(ident,max(0.,min(1.,segments[1])))
        command=row.get('Command','')
        if not isinstance(command,str):return
        for part in command.split(';')[:64]:
            tokens=part.strip().split(maxsplit=1)
            if len(tokens)!=2 or tokens[0]!='start_mtn':continue
            group,_,name=tokens[1].strip().partition(':')
            visit(group,name,depth+1)
    visit(root)
    return result
