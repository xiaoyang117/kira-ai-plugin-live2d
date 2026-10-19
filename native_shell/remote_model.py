"""Portable model archive shared by the plugin and the standalone shell."""
import copy
import hashlib
import json
from pathlib import Path,PurePosixPath
import shutil
import zipfile
import uuid

MAX_SIZE=1024*1024*1024

def safe_member(name):
    p=PurePosixPath(name.replace('\\','/'))
    if p.is_absolute() or not p.parts or any(x in ('..','') or ':' in x for x in p.parts):
        raise ValueError('模型包包含无效路径')
    return p.as_posix()

def make_model_bundle(model,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    stage=Path(model['path']).parent.resolve();source=Path(model['original']).parent.resolve()
    portable=copy.deepcopy(model);portable['path']='model/'+Path(model['path']).name;portable['original']='source/model.json'
    files={};aliases={};motions={}
    files[portable['path']]=Path(model['path'])
    for path in (stage/'assets').rglob('*'):
        if path.is_file():
            if not path.resolve().is_relative_to(stage):raise ValueError('模型资源越界')
            files['model/'+path.relative_to(stage).as_posix()]=path
    for original,staged in model['motion_files'].items():
        relative=Path(original).resolve().relative_to(source).as_posix()
        name=safe_member('source/'+relative);target='model/'+Path(staged).resolve().relative_to(stage).as_posix()
        files[name]=Path(staged);motions[name]=target;aliases[original]=name
    portable['motion_files']=motions
    for rows in portable.get('motion_entries',{}).values():
        for row in rows:
            if isinstance(row,dict) and row.get('File'):
                row['File']=(source/row['File']).resolve().relative_to(source).as_posix()
    metadata={'model':portable,'motion_aliases':aliases}
    temporary=folder/('preparing-'+uuid.uuid4().hex+'.zip')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo('remote-model.json'),json.dumps(metadata,ensure_ascii=False,sort_keys=True))
        archive.writestr(zipfile.ZipInfo('source/model.json'),'{}')
        for name,path in sorted(files.items()):
            info=zipfile.ZipInfo(safe_member(name));info.compress_type=zipfile.ZIP_DEFLATED
            with archive.open(info,'w') as dest,path.open('rb') as src:shutil.copyfileobj(src,dest)
    h=hashlib.sha256()
    with temporary.open('rb') as data:
        while chunk:=data.read(1024*1024):h.update(chunk)
    digest=h.hexdigest();target=folder/(digest+'.zip')
    if target.exists():temporary.unlink()
    else:temporary.replace(target)
    return target,digest

def unpack_model_bundle(archive,folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as data:
        rows=data.infolist()
        if len(rows)>8192 or sum(x.file_size for x in rows)>MAX_SIZE:raise ValueError('模型包过大')
        for row in rows:
            name=safe_member(row.filename)
            if row.is_dir():continue
            path=folder/name
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.resolve().is_relative_to(folder):raise ValueError('模型包路径越界')
            with data.open(row) as src,path.open('wb') as dest:shutil.copyfileobj(src,dest)
    config=json.loads((folder/'remote-model.json').read_text(encoding='utf-8'))
    model=config['model']
    def local(name):return str(folder/safe_member(name))
    model['path']=local(model['path']);model['original']=local(model['original'])
    model['motion_files']={local(k):local(v) for k,v in model['motion_files'].items()}
    return model,{key:local(value) for key,value in config['motion_aliases'].items()}
