"""Prepare a standard Cubism model without changing original resources."""
import copy
import math
import hashlib
import json
from pathlib import Path
import shutil
from ..model_profile import load_profile,read_json,model_asset_kind
from ..motion_analysis import add_discovered
from .initial_pose import initial_part_opacities

BREATH_STRENGTH = 0.0


def soften_motion_breath(motion, strength=BREATH_STRENGTH):
    """Disable standard breath values by default, including Bezier control points.

    Adapt the generated motion before SDK physics sees it; retain all keyframe
    times, other parameters and the user's original motion file.
    """
    result=copy.deepcopy(motion)
    for curve in result.get('Curves',[]):
        if curve.get('Target')!='Parameter' or curve.get('Id') not in ('ParamBreath','PARAM_BREATH'):
            continue
        segments=curve.get('Segments')
        if not isinstance(segments,list) or len(segments)<2:
            continue
        indices=[1];offset=2
        while offset<len(segments):
            kind=segments[offset]
            if kind not in (0,1,2,3):
                indices=[];break
            size=6 if kind==1 else 2
            if offset+size>=len(segments):
                indices=[];break
            indices.extend(range(offset+2,offset+size+1,2))
            offset+=size+1
        if not all(isinstance(segments[index],(int,float)) and math.isfinite(segments[index]) for index in indices):
            continue
        for index in indices:
            segments[index]*=strength
    return result


def normalize_motion_counts(motion):
    """SDK allocations trust Meta counts; rebuild them from validated curve data."""
    result=copy.deepcopy(motion)
    curves=result.get('Curves')
    if not isinstance(curves,list) or not isinstance(result.get('Meta'),dict):
        raise ValueError('动作缺少有效的 Curves / Meta')
    for field in ('Duration','Fps'):
        if field in result['Meta'] and (type(result['Meta'][field]) not in (int,float)
                or not math.isfinite(result['Meta'][field]) or result['Meta'][field]<=0):
            raise ValueError('动作的时长或帧率无效')
    segment_count=point_count=0
    for curve in curves:
        if (not isinstance(curve,dict) or not isinstance(curve.get('Id'),str) or not curve['Id']
                or curve.get('Target') not in ('Parameter','Model','PartOpacity')):
            raise ValueError('动作曲线的目标或参数名称无效')
        values=curve.get('Segments') if isinstance(curve,dict) else None
        if (not isinstance(values,list) or len(values)<2
                or not all(type(v) in (int,float) and math.isfinite(v) for v in values)):
            raise ValueError('动作曲线的关键帧数据无效')
        point_count+=1;offset=2
        while offset<len(values):
            kind=values[offset]
            if kind not in (0,1,2,3):
                raise ValueError('动作曲线含有未知的线段类型')
            size=7 if kind==1 else 3
            if offset+size>len(values):
                raise ValueError('动作曲线的线段数据不完整')
            segment_count+=1;point_count+=3 if kind==1 else 1
            offset+=size
    events=result.get('UserData',[])
    if not isinstance(events,list) or any(not isinstance(v,dict) or not isinstance(v.get('Value'),str) for v in events):
        raise ValueError('动作事件数据无效')
    result['Meta'].update(CurveCount=len(curves),TotalSegmentCount=segment_count,
        TotalPointCount=point_count,UserDataCount=len(events),
        TotalUserDataSize=sum(len(event['Value'].encode('utf-8')) for event in events))
    return result


def prepare_model(source, data_dir):
    source=Path(source).resolve()
    data_dir=Path(data_dir).resolve()
    profile=add_discovered(load_profile(str(source)))
    source=Path(profile['load_path']) if profile['load_path'] else Path(source)
    original=read_json(source)
    if 'FileReferences' not in original:
        raise ValueError('独立壳当前支持普通 .model3.json 模型；LPK 请先解包')
    refs=copy.deepcopy(original['FileReferences'])
    if not isinstance(refs,dict) or not isinstance(refs.get('Moc'),str):
        raise ValueError('模型的 FileReferences / Moc 格式无效')
    for field,kind,empty in (('Textures',list,[]),('Expressions',list,[]),('Motions',dict,{})):
        if refs.get(field) is None:refs[field]=empty
        if not isinstance(refs.get(field),kind):raise ValueError('模型的 '+field+' 格式无效')
    if any(not isinstance(value,str) for value in refs['Textures']):
        raise ValueError('模型纹理路径必须是字符串')
    for section in ('Expressions','Motions'):
        entries=refs[section] if section=='Expressions' else [item for rows in refs[section].values() if isinstance(rows,list) for item in rows]
        if section=='Motions' and any(not isinstance(rows,list) for rows in refs[section].values()):
            raise ValueError('模型动作组必须是列表')
        if any(isinstance(item,dict) and item.get('File') is not None and not isinstance(item['File'],str) for item in entries):
            raise ValueError('模型表情或动作的 File 路径必须是字符串')
    base=source.parent.resolve()
    target=Path(data_dir)/'native-models'/hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:20]
    target.mkdir(parents=True,exist_ok=True)
    def resource(value):
        if not isinstance(value,str) or not value:
            raise ValueError('模型资源路径无效')
        path=(base/value).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            raise ValueError('模型资源缺失或超出模型目录：'+value)
        # Native SDK file APIs on Windows require predictable ASCII resource paths.
        suffix=path.suffix.lower()
        if not suffix.isascii() or not suffix[1:].isalnum() or len(suffix)>16:suffix='.bin'
        for ending in ('.motion3.json','.exp3.json','.physics3.json','.pose3.json','.cdi3.json'):
            if path.name.lower().endswith(ending):suffix=ending;break
        relative=Path('assets')/(hashlib.sha256(str(path).encode()).hexdigest()[:24]+suffix)
        dest=target/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        stat=path.stat()
        if path.suffix.lower()=='.json' and model_asset_kind(str(path),stat.st_mtime_ns,stat.st_size)=='motion':
            original_motion=read_json(path)
            try:adapted=soften_motion_breath(normalize_motion_counts(original_motion))
            except ValueError as exc:raise ValueError('动作资源无法安全加载：'+value+'：'+str(exc)) from exc
            if adapted!=original_motion:
                content=json.dumps(adapted,ensure_ascii=True,indent=2)+'\n'
                if not dest.is_file() or dest.read_bytes()!=content.encode('utf-8'):
                    dest.write_text(content,encoding='utf-8')
                return relative.as_posix()
        if not dest.is_file() or (path.stat().st_size,path.stat().st_mtime_ns)!=(dest.stat().st_size,dest.stat().st_mtime_ns):
            shutil.copy2(path,dest)
        return relative.as_posix()
    clean={'Moc':resource(refs['Moc']),
        'Textures':[resource(v) for v in refs.get('Textures',[])]}
    for key in ('Physics','Pose','DisplayInfo'):
        if refs.get(key):clean[key]=resource(refs[key])
    expressions=[];expression_names={}
    for item in refs.get('Expressions',[]):
        if not isinstance(item,dict) or not isinstance(item.get('File'),str):continue
        path=(base/item['File']).resolve()
        if not path.is_file():continue
        stat=path.stat()
        if model_asset_kind(str(path),stat.st_mtime_ns,stat.st_size)!='expression':continue
        index=len(expressions);expression_names[str(item.get('Name') or '')]=index
        expressions.append({'Name':str(index),'File':resource(item['File'])})
    clean['Expressions']=expressions
    groups={}
    for group,items in refs.get('Motions',{}).items():
        if not isinstance(items,list):continue
        motions=[]
        for item in items:
            value=item.get('File') if isinstance(item,dict) else None
            if not value:continue
            path=(base/value).resolve()
            if not path.is_file():continue
            stat=path.stat()
            if model_asset_kind(str(path),stat.st_mtime_ns,stat.st_size)!='motion':continue
            # The native loader crashes on per-entry fade overrides in some models.
            # Let the motion's own fade values/defaults control blending instead.
            motions.append({'File':resource(value)})
        if motions:
            # SDK group formatting must also stay ASCII, like staged file names.
            native_group=group if group.isascii() else 'kira_group_'+hashlib.sha256(group.encode()).hexdigest()
            groups[native_group]=motions
    clean['Motions']=groups
    motion_files={}
    for spec in profile['motions'].values():
        if spec['type']==1:
            motion_path=Path(spec['mtn']).resolve()
            if motion_path.is_relative_to(base) and motion_path.is_file():
                stat=motion_path.stat()
                if model_asset_kind(str(motion_path),stat.st_mtime_ns,stat.st_size)!='motion':continue
                motion_files[str(motion_path)]=str(target/resource(str(motion_path.relative_to(base))))
    for items in refs.get('Motions',{}).values():
        for item in items if isinstance(items,list) else []:
            if isinstance(item,dict) and item.get('File'):
                motion_path=(base/item['File']).resolve()
                if motion_path.is_relative_to(base) and motion_path.is_file():
                    stat=motion_path.stat()
                    if model_asset_kind(str(motion_path),stat.st_mtime_ns,stat.st_size)!='motion':continue
                    motion_files[str(motion_path)]=str(target/resource(item['File']))
    output={'Version':3,'FileReferences':clean}
    for key in ('Groups','HitAreas','Layout'):
        if key in original:output[key]=original[key]
    path=target/'native.model3.json';path.write_text(json.dumps(output,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    return {'path':str(path),'original':str(source.resolve()),'expressions':expressions,
        'expression_names':expression_names,'motion_files':motion_files,'motion_entries':refs.get('Motions',{}),
        'hit_areas':output.get('HitAreas',[]),'drag_candidates':profile.get('drag_candidates',[]),
        'initial_parts':initial_part_opacities(source,original)}
