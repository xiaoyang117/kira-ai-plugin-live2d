"""Create an optional, reversible native AI-control copy; never edit the source."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading

from .model_profile import read_json

COPY_LOCK=threading.Lock()

AUDIO={'.wav','.ogg','.mp3','.flac','.m4a','.opus','.aac','.wma'}
BLOCKED={'sound','voice','text','command','postcommand','paramtrigger','areatrigger','handtrigger',
         'minmtn','maxmtn','beginmtn','endmtn','entermtn','exitmtn','userdata'}


def clean(value,folder):
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            normalized=key.replace('_','').casefold()
            if normalized=='motions' and isinstance(item,dict):
                result[key]={group:clean(entries,folder) for group,entries in item.items()}
                continue
            if normalized in BLOCKED:continue
            if normalized=='file' and isinstance(item,str) and Path(item).suffix.lower() in AUDIO:continue
            result[key]=clean(item,folder)
        return result
    if isinstance(value,list):return [clean(item,folder) for item in value]
    if isinstance(value,str) and Path(value).is_absolute():
        path=Path(value).resolve()
        if path.is_relative_to(folder):return path.relative_to(folder).as_posix()
    return value


def inventory(folder):
    rows=[];size=0
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('模型目录包含链接，请使用完整独立的模型文件夹')
        if path.is_file():
            stat=path.stat();size+=stat.st_size
            rows.append([path.relative_to(folder).as_posix(),stat.st_size,stat.st_mtime_ns])
            if size>2*1024**3 or len(rows)>10000:raise ValueError('模型目录超过 2 GB 或 10000 个文件')
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()


def make_copy(source,data_dir):
    with COPY_LOCK:
        return _make_copy(source,data_dir)


def _make_copy(source,data_dir):
    source=Path(source).resolve();folder=source.parent
    root=Path(data_dir).resolve()/'native-ai-copies'
    if root==folder or root.is_relative_to(folder) or folder.is_relative_to(root):
        raise ValueError('AI 控制副本目录必须与原模型目录分开')
    signature=inventory(folder)
    key=hashlib.sha256((str(source).casefold()+signature+'native-v1').encode()).hexdigest()[:32]
    target=root/key
    try:
        info=read_json(target/'adaptation.json')
        if (info['source_signature']==signature and info['copy_signature']==inventory(target/'model')
                and Path(info['backup_path']).is_file() and Path(info['model_path']).is_file()):
            return {**info,'reused':True}
    except (OSError,ValueError,KeyError,TypeError):pass
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.preparing-',dir=root) as temporary:
        stage=Path(temporary);copied=stage/'model';copied.mkdir()
        raw=source.read_bytes();(stage/'original-config.backup.json').write_bytes(raw)
        removed=0
        for file in sorted(folder.rglob('*')):
            if not file.is_file():continue
            if file.suffix.lower() in AUDIO:removed+=1;continue
            destination=copied/file.relative_to(folder);destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(file,destination)
            if file.suffix.lower()=='.json':
                try:data=read_json(file)
                except ValueError:continue
                if file==source or isinstance(data.get('Curves'),list):
                    data=clean(copy.deepcopy(data),folder)
                    if isinstance(data.get('Meta'),dict):
                        for field in ('UserDataCount','TotalUserDataSize'):
                            if field in data['Meta']:data['Meta'][field]=0
                    if file==source:data['KiraAIAdaptation']={'version':1,'mode':'native','original':str(source)}
                    destination.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        from .native_shell.model import prepare_model
        prepare_model(copied/source.name,stage/'validation')
        if source.read_bytes()!=raw or inventory(folder)!=signature:
            raise ValueError('原模型在生成副本期间发生变化，请重试')
        info={'version':1,'original':str(source),'source_signature':signature,
              'model_path':str(target/'model'/source.name),
              'backup_path':str(target/'original-config.backup.json'),
              'copy_signature':inventory(copied),'removed_audio':removed}
        (stage/'adaptation.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        # Keep a broken older cache recoverable rather than overwriting it.
        if target.exists():
            import uuid
            target.rename(root/(key+'-previous-'+uuid.uuid4().hex[:8]))
        # Validation output is just temporary native staging, not part of the saved copy.
        shutil.rmtree(stage/'validation')
        stage.rename(target)
        return {**info,'reused':False}


def prepare_render_model(source,data_dir,enabled=True,progress=lambda state:None):
    from .native_shell.model import prepare_model
    source=Path(source).resolve();render_source=source
    state={'stage':'disabled','message':'使用普通 JSON 模型','enabled':False}
    if enabled:
        progress({'stage':'preparing','message':'正在生成或检查 AI 控制副本…','enabled':True})
        try:
            result=make_copy(source,data_dir);render_source=Path(result['model_path'])
            state={**result,'stage':'prepared','message':'AI 控制副本已准备，等待模型加载','enabled':True}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            state={'stage':'error','message':'AI 控制副本生成失败，已使用原模型：'+str(exc),'enabled':True}
    model=prepare_model(render_source,data_dir)
    if render_source!=source:
        # Public mappings keep original paths; the renderer plays the cleaned staged resources.
        copy_folder=render_source.parent
        model['motion_files']={str(source.parent/Path(key).relative_to(copy_folder)):value
                               for key,value in model['motion_files'].items()}
        model['original']=str(source)
    from .native_shell.initial_pose import initial_part_opacities
    model['initial_parts']=initial_part_opacities(source)
    preferences=Path(data_dir)/'native-models'/hashlib.sha256(str(source).encode()).hexdigest()[:20]/'window.json'
    preferences.parent.mkdir(parents=True,exist_ok=True)
    return model,state,str(preferences)
