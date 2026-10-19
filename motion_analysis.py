"""Read-only, deterministic resource discovery and semantic hints."""
import copy
from functools import lru_cache
from itertools import islice
import json
from pathlib import Path
import re
from .model_profile import read_json,model_asset_kind,unique,read_overrides

EMOTIONS={'开心':('开心','高兴','happy','joy','smile','微笑'),'生气':('生气','angry','anger'),
 '难过':('难过','悲伤','sad'),'惊讶':('惊讶','surprise'),'害羞':('害羞','shy','blush','脸红'),
 '俏皮':('俏皮','playful','wink'),'点头':('点头','nod'),'摇头':('摇头','shake'),
 '歪头':('歪头','tilt'),'待机':('待机','idle','standby','breath')}
APPEARANCE=re.compile(r'服|衣|裙|帽|袜|鞋|水印|套装|换装|costume|cloth|outfit|dress|skirt|watermark|accessor|sleeve|stocking|swimsuit|bikini|panties|underwear|glasses|ribbon|shoe|sock|胸罩|内裤|内衣|披风|围巾|眼镜|饰品|发饰|(?:^|param|part|[^a-z])(?:hat|cap|bra)(?:$|[^a-z])',re.I)
PINYIN_APPEARANCE=re.compile(r'(?:^|[^a-z])(?:yifu|zhifu|sifu|changfu|monvfu|wanshengjiefu|maozi|qunzi|wazi|xiezi)(?:[0-9]*)(?:$|[^a-z])',re.I)
FACE_PARAMETER=re.compile(r'^param(?:eye|brow|mouth|cheek|angle|body|breath)',re.I)
def appearance_name(text):return bool(APPEARANCE.search(text) or PINYIN_APPEARANCE.search(text))

PARAMS={'paramanglex':'头部左右转动','paramangley':'头部上下转动','paramanglez':'头部倾斜',
 'parambodyanglex':'身体左右转动','parambodyangley':'身体前后倾斜','parambodyanglez':'身体侧倾',
 'parameyelopen':'左眼开合','parameyeropen':'右眼开合','parameyelsmile':'左眼笑意','parameyersmile':'右眼笑意',
 'parameyeballx':'视线左右','parameyebally':'视线上下','parammouthform':'嘴型情绪','parammouthopeny':'嘴部开合',
 'paramcheek':'脸红','parambreath':'呼吸'}

def clean_id(value):return re.sub(r'[^a-z0-9]','',str(value).lower())

def curve_values(segments):
    if not isinstance(segments,list) or len(segments)<2:return []
    values=[segments[1]];i=2
    while i<len(segments):
        kind=segments[i]
        if type(kind) not in (int,float):break
        width=7 if kind==1 else 3 if kind in (0,2,3) else 0
        if not width or i+width>len(segments):break
        values.extend(segments[i+2:i+width:2]);i+=width
    return [float(v) for v in values if type(v) in (int,float)]

@lru_cache(maxsize=1024)
def asset_analysis(path,mtime,size):
    data=read_json(Path(path));parameters=[];pose_parameters=[];parts=[];active_parameters=[]
    if isinstance(data.get('Parameters'),list):
        parameters=[p.get('Id') for p in data['Parameters'] if isinstance(p,dict)]
        for item in data['Parameters']:
            if not isinstance(item,dict):continue
            value=item.get('Value');blend=item.get('Blend','Add')
            if type(value) in (int,float) and (blend=='Overwrite' or (blend=='Add' and value!=0) or (blend=='Multiply' and value!=1)):
                active_parameters.append(item.get('Id'))
    elif isinstance(data.get('Curves'),list):
        for curve in data['Curves']:
            if not isinstance(curve,dict):continue
            values=curve_values(curve.get('Segments'))
            if curve.get('Target')=='PartOpacity' and values:
                parts.append(curve.get('Id'))
            elif curve.get('Target')=='Parameter':
                if values and max(values)-min(values)>1e-5:parameters.append(curve.get('Id'))
                elif values and any(abs(value)>1e-5 for value in values):pose_parameters.append(curve.get('Id'))
    appearance_ids=list(dict.fromkeys(p for p in (active_parameters if isinstance(data.get('Parameters'),list) else parameters+pose_parameters+parts) if isinstance(p,str)))[:512]
    parameters=list(dict.fromkeys(p for p in parameters if isinstance(p,str)))[:64]
    duration=data.get('Meta',{}).get('Duration') if isinstance(data.get('Meta'),dict) else None
    if type(duration) not in (int,float) or not 0<=duration<=600:duration=None
    return {'parameters':parameters,'appearance_ids':appearance_ids,'active_parameters':[p for p in active_parameters if isinstance(p,str)][:512],'pose_parameters':list(dict.fromkeys(p for p in pose_parameters if isinstance(p,str)))[:128],
            'parts':list(dict.fromkeys(p for p in parts if isinstance(p,str)))[:128],
            'duration':duration,'loop':data.get('Meta',{}).get('Loop') is True if isinstance(data.get('Meta'),dict) else False}


def limb_labels(ids):
    labels=[]
    for ident in ids:
        key=clean_id(ident)
        side='左' if 'left' in key else '右' if 'right' in key else ''
        for token,label in (('shoulder','肩'),('wrist','手腕'),('arm','手臂'),('hand','手'),('leg','腿'),('foot','脚')):
            if token in key:
                value=side+label
                if value not in labels:labels.append(value)
                break
    return labels


def playback_hint(info, section):
    if section=='expressions':return '表情状态持续至后续切换或恢复默认'
    hints=[]
    if info.get('duration') is not None:hints.append(f"片段 {info['duration']:g} 秒")
    if info.get('loop'):hints.append('文件标记循环')
    if info.get('parts'):hints.append('部件显隐状态保留，后续动作可改写')
    elif info.get('duration') is not None:hints.append('片段结束不代表姿态自动恢复')
    return '；'.join(hints)

@lru_cache(maxsize=32)
def discovered(directory,stamp):
    base=Path(directory);result=[]
    for path in islice(base.rglob('*.motion3.json'),512):
        try:
            path=path.resolve()
            if not path.is_relative_to(base):continue
            st=path.stat()
            if model_asset_kind(str(path),st.st_mtime_ns,st.st_size)=='motion':result.append(str(path))
        except (OSError,ValueError):continue
    return result

def motion_path(profile,spec,data=None):
    source=Path(profile['load_path']);base=source.parent
    if spec['type']==1:return Path(spec['mtn']),None
    if data is None:data=read_json(source)
    group,_,name=spec['mtn'].partition(':')
    rows=data.get('FileReferences',data).get('Motions',{}).get(group,[])
    entries=[r for r in rows if isinstance(r,dict) and (not name or r.get('Name',r.get('name'))==name)]
    if not entries:return None,None
    row=entries[0]
    return (base/row['File']).resolve() if row.get('File') else None,row.get('Expression',row.get('expression'))

def add_discovered(profile,overrides=''):
    if not profile.get('load_path') or read_overrides(overrides)['motions']:return profile
    source=Path(profile['load_path']);base=source.parent.resolve()
    if profile.get('format')!='Cubism 3':return profile
    profile=copy.deepcopy(profile)
    known=set();data=read_json(source)
    for spec in profile['motions'].values():
        try:
            path,_=motion_path(profile,spec,data)
            if path:known.add(str(path.resolve()).casefold())
        except (OSError,ValueError,KeyError):pass
    for value in discovered(str(base),source.stat().st_mtime_ns):
        if value.casefold() in known or len(profile['motions'])>=512:continue
        path=Path(value);name='发现动作/'+path.name.removesuffix('.motion3.json')
        profile['motions'][unique(profile['motions'],name)]={'type':1,'mtn':value}
    return profile

def catalog(profile):
    source=Path(profile['load_path']) if profile.get('load_path') else None
    if source is None:return {'expressions':{},'motions':{}}
    data=read_json(source);refs=data.get('FileReferences',data);base=source.parent.resolve()
    expressions=[];outfit_parameters=set()
    for item in refs.get('Expressions',[]):
        try:
            path=(base/item['File']).resolve();st=path.stat()
            if path.is_relative_to(base) and model_asset_kind(str(path),st.st_mtime_ns,st.st_size)=='expression':
                expressions.append(path)
                if appearance_name(str(item.get('Name',''))+' '+path.stem):
                    known=asset_analysis(str(path),st.st_mtime_ns,st.st_size)
                    outfit_parameters.update(p for p in known.get('active_parameters',[]) if not FACE_PARAMETER.search(p))
        except (OSError,TypeError,ValueError,KeyError):continue
    display={}
    try:
        path=(base/refs.get('DisplayInfo','')).resolve()
        if path.is_relative_to(base) and path.is_file():
            labels=read_json(path)
            for section in ('Parameters','Parts'):
                display.update({p['Id']:str(p.get('Name','')) for p in labels.get(section,[]) if isinstance(p,dict) and isinstance(p.get('Id'),str)})
    except (OSError,ValueError,TypeError):pass
    result={'expressions':{},'motions':{}}
    for section in result:
        for name,spec in profile[section].items():
            info={'name':name,'tags':[],'summary':'用途不明确，请先预览确认','parameters':[],'duration':None,'appearance':appearance_name(name),'uncertain':True}
            try:
                path=expressions[spec] if section=='expressions' and 0<=spec<len(expressions) else None
                linked=None
                if section=='motions':path,linked=motion_path(profile,spec,data)
                if path:
                    path=path.resolve()
                    if not path.is_relative_to(base):raise ValueError('资源不属于模型')
                    st=path.stat();info.update(asset_analysis(str(path),st.st_mtime_ns,st.st_size))
                ids=info.get('appearance_ids',info['parameters'])
                search=' '.join([name,path.stem if path else '',linked or '',*ids,*[display.get(p,'') for p in ids]])
                info['appearance']=appearance_name(search)
                shared=set(info.get('active_parameters',[]))&outfit_parameters
                if shared:
                    info['appearance']=True
                    info['appearance_evidence']='同时修改已知换装资源的参数：'+'、'.join(sorted(shared)[:8])
                info['tags']=[tag for tag,tokens in EMOTIONS.items() if any(t in search.casefold() for t in tokens)]
                meanings=list(dict.fromkeys(PARAMS[clean_id(p)] for p in info['parameters'] if clean_id(p) in PARAMS))
                parts=info.get('parts',[])
                hands=[label for label in limb_labels(parts) if label in ('左手','右手','手')]
                limbs=limb_labels(info['parameters']+info.get('pose_parameters',[]))
                effects=[]
                if hands:effects.append('手型切换（'+'、'.join(hands)+'）')
                if parts and not hands:effects.append('部件显隐切换（'+str(len(parts))+' 项）')
                if limbs:effects.append('肢体姿态（'+'、'.join(limbs[:6])+'）')
                if info['appearance']:summary='外观／换装资源，普通情绪回应不要自动使用'+('；'+info['appearance_evidence'] if info.get('appearance_evidence') else '')
                else:
                    summary='；'.join(effects+info['tags'])
                    if meanings:summary+=('；其他变化参数：' if summary else '变化参数：')+'、'.join(meanings[:5])
                    summary=summary or info['summary']
                info['playback_hint']=playback_hint(info,section)
                if linked:summary+='；关联表情：'+linked
                info['summary']=summary[:240]
                info['uncertain']=not bool(info['tags'] or meanings or hands or limbs) or info['appearance']
            except (OSError,ValueError,KeyError,IndexError,TypeError):pass
            result[section][name]=info
    return result
