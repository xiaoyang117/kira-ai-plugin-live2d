"""Pinned LpkUnpacker engine downloaded only on the first LPK import."""
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen
import zipfile

from .model_library import MAX_BYTES, MAX_FILES, safe_relative
from .model_profile import read_json

REVISION = '906d4cdd5597403ebf46dde8fb47d9c81a352d19'
BASE_URL = f'https://raw.githubusercontent.com/ihopenot/LpkUnpacker/{REVISION}/'
WHEEL = 'filetype-1.2.0-py2.py3-none-any.whl'
ASSETS = {
    'LpkUnpacker.py': (BASE_URL+'LpkUnpacker.py', '1acd7ab8e3ee6f4e2169eb567df96a8ab9b7a36b45f771698a2402c5177116be'),
    'Core/lpk_loader.py': (BASE_URL+'Core/lpk_loader.py', '72babad891d18357fbfe5f176ee83658d5624b263e99787c2b2e4cda3c2939fe'),
    'Core/utils.py': (BASE_URL+'Core/utils.py', '2c32a7f0dfd5c84ad8fd2d6380ee951dd4cc63173251ecd3ae567fe9650b68d5'),
    WHEEL: ('https://files.pythonhosted.org/packages/18/79/1b8fa1bb3568781e84c9200f951c735f3f157429f44be0495da55894d620/'+WHEEL,
        '7ce71b6880181241cf7ac8697a2f1eb6a8bd9b429f7ad6d27b8db9ba5f1c2d25'),
}


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def engine_folder(data_dir):
    return Path(data_dir) / 'components' / ('lpkunpacker-'+REVISION[:12])


def engine_ready(folder):
    try:
        return all((Path(folder)/name).is_file() and file_hash(Path(folder)/name)==digest
                   for name, (_,digest) in ASSETS.items())
    except OSError:
        return False


def ensure_engine(folder, progress=lambda stage,message:None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    if engine_ready(folder):return folder
    progress('downloading','首次使用正在下载并校验 LpkUnpacker，完成后自动解包…')
    for name,(url,digest) in ASSETS.items():
        target=folder/name
        if target.is_file() and file_hash(target)==digest:continue
        try:
            with urlopen(url,timeout=25) as response:raw=response.read(1024*1024+1)
        except (OSError,HTTPException) as exc:
            raise ValueError('解包组件下载失败，请检查 GitHub / PyPI 网络后重试；原文件未改动') from exc
        if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('解包组件校验失败，已停止运行，请重试')
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix('.download');temporary.write_bytes(raw);temporary.replace(target)
    return folder


def unpack_lpk(package, output, data_dir, progress=lambda stage,message:None):
    package,output=Path(package).resolve(),Path(output).resolve()
    config=None
    for candidate in sorted(package.parent.glob('*.json')):
        try:
            value=read_json(candidate)
            if str(value.get('lpkFile') or value.get('file') or '').casefold()==package.name.casefold():
                config=candidate;break
        except (ValueError,OSError):continue
    if config is None:
        fallback=package.parent/'config.json'
        if fallback.is_file():
            try:
                value=read_json(fallback)
                if value.get('fileId') or value.get('lpkFile'):config=fallback
            except (ValueError,OSError):pass
    with zipfile.ZipFile(package) as archive:
        entries=archive.infolist()
        if len(entries)>MAX_FILES or sum(item.file_size for item in entries)>MAX_BYTES:
            raise ValueError('LPK 解包后超过 512 MB 或 4096 个文件')
        for item in entries:
            if item.is_dir():continue
            safe_relative(item.filename)
            if (item.external_attr>>16)&0o170000==0o120000:
                raise ValueError('LPK 不支持符号链接')
        for name in ('config.mlve',hashlib.md5(b'config.mlve').hexdigest()):
            if name in archive.namelist():
                if archive.getinfo(name).file_size>1024*1024:raise ValueError('LPK 配置过大')
                meta=json.loads(archive.read(name).decode('utf-8-sig'))
                if meta.get('type')=='STM_1_0' and config is None:
                    raise ValueError('创意工坊 LPK 缺少对应的 config.json，请将两者一起选择或拖入')
                break
    engine=ensure_engine(engine_folder(data_dir),progress)
    progress('unpacking','正在解包 '+package.name+'，请稍候…')
    output.mkdir(parents=True,exist_ok=True)
    log_path=output.parent/(output.name+'-unpack.log')
    try:
        with log_path.open('wb') as log:
            result=subprocess.run([sys.executable,'-I','-X','utf8',str(Path(__file__).with_name('lpk_host.py')),
                str(engine.resolve()),str(package),str(config) if config else '',str(output)],
                cwd=output,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=180,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError('LPK 解包超过 3 分钟，已停止；原文件未改动') from exc
    if result.returncode:
        raise ValueError('LPK 解包失败，可能缺少有效 config.json 或此格式不受支持；当前模型未更改')
    count=total=0
    for path in output.rglob('*'):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('解包结果包含不支持的链接')
        if path.is_file():
            count+=1;total+=path.stat().st_size
            safe_relative(path.relative_to(output).as_posix())
    if count>MAX_FILES or total>MAX_BYTES:raise ValueError('LPK 解包结果超过资源上限')
