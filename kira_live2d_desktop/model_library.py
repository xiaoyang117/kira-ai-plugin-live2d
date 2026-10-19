"""Import complete model folders/archives without changing their source files."""
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 4096


def safe_relative(name):
    name = name.replace('\\', '/')
    path = PurePosixPath(name)
    if (not name or name.startswith('/') or not path.parts or len(name) > 1024
            or any(part in ('.', '..') or ':' in part or part.endswith((' ', '.'))
                   or re.search(r'[<>"|?*\x00-\x1f]', part)
                   or part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                       *('COM'+str(n) for n in range(1, 10)), *('LPT'+str(n) for n in range(1, 10))}
                   for part in name.split('/'))):
        raise ValueError('模型文件名或目录无效：'+name[:100])
    return Path(*path.parts)


class ModelLibrary:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / 'model-library'

    @staticmethod
    def indexed(folder):
        try:
            data=json.loads((folder/'.kira-models.json').read_text(encoding='utf-8'))
            paths=[folder/safe_relative(name) for name in data['models']]
            if paths and all(path.suffix.lower()=='.json' and path.is_file() for path in paths):return paths
        except (OSError,ValueError,KeyError,TypeError):pass
        return []

    def original_source(self, path):
        from .model_profile import read_json
        seen=set()
        for _ in range(8):
            identity=str(path).casefold()
            if identity in seen:break
            seen.add(identity)
            managed=any(path.is_relative_to(self.root.parent/name) for name in ('ai-models','native-ai-copies'))
            if not managed or path.parent.name!='model':break
            try:
                info=read_json(path.parent.parent/'adaptation.json')
                if str(Path(info['model_path']).resolve()).casefold()!=identity:break
                source=Path(info['original'])
                if not source.is_absolute() or source.suffix.lower()!='.json':break
                path=source.resolve()
            except (OSError,ValueError,KeyError,TypeError):break
        return path

    def items(self, follower, current=''):
        paths = [current] if current else []
        if follower:
            paths.extend(item.get('path', '') for item in follower.models.values())
        if self.root.is_dir():
            for folder in sorted(self.root.iterdir()):
                if folder.is_dir() and re.fullmatch('[0-9a-f]{32}',folder.name):
                    paths.extend(str(p) for p in (self.indexed(folder) or sorted(folder.rglob('*.model3.json'))))
        from .model_profile import read_json
        seen = set(); result = []
        for value in paths:
            if not value:continue
            path = Path(value).resolve()
            if path.suffix.lower()!='.json':continue
            available=path.is_file()
            if available:
                try:
                    raw=read_json(path);refs=raw.get('FileReferences')
                    if not isinstance(refs,dict) or not isinstance(refs.get('Moc'),str):continue
                except (OSError,ValueError):continue
            source=self.original_source(path);identity=str(source).casefold()
            if identity in seen:continue
            seen.add(identity)
            name=source.name.removesuffix('.model3.json').removesuffix('.json')
            if re.fullmatch('model[0-9]+',name,re.IGNORECASE):name=source.parent.name+' · '+name
            result.append({'path': str(path), 'name': name,
                           'available': available, 'current': bool(current) and str(path).casefold() == str(Path(current).resolve()).casefold()})
        return result

    def import_files(self, uploads, names, progress=lambda stage,message:None):
        from .native_shell.model import prepare_model
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.import-', dir=self.root) as temporary:
            stage = Path(temporary); content = stage / 'files'; content.mkdir()
            total = 0; count = 0; seen = set()

            def write(name, source):
                nonlocal total, count
                relative = safe_relative(name)
                if relative.parts[0].startswith('.kira-'):raise ValueError('模型目录使用了插件保留的文件名')
                identity = relative.as_posix().casefold()
                if identity in seen:
                    raise ValueError('模型中存在重复文件：'+name)
                seen.add(identity); count += 1
                if count > MAX_FILES:
                    raise ValueError('模型文件数量超过 4096 个')
                target = content / relative; target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('wb') as output:
                    while chunk := source.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise ValueError('模型解压后或文件总大小超过 512 MB')
                        output.write(chunk)

            if len(uploads) == 1 and names[0].lower().endswith(('.zip','.wpk')):
                with zipfile.ZipFile(uploads[0].file) as archive:
                    if len(archive.infolist()) > MAX_FILES * 2:
                        raise ValueError('压缩包文件数量过多')
                    for member in archive.infolist():
                        if member.is_dir() or member.filename.startswith('__MACOSX/'):
                            continue
                        if (member.external_attr >> 16) & 0o170000 == 0o120000:
                            raise ValueError('压缩包不能包含符号链接')
                        if member.file_size > MAX_BYTES or total + member.file_size > MAX_BYTES:
                            raise ValueError('模型解压后超过 512 MB')
                        with archive.open(member) as source:
                            write(member.filename, source)
            else:
                for upload, name in zip(uploads, names):
                    upload.file.seek(0)
                    write(name, upload.file)
            # Use input content identity so a repeated LPK import reuses its unpacked model/config.
            digest = hashlib.sha256()
            for file in sorted(content.rglob('*')):
                if file.is_file():
                    digest.update(file.relative_to(content).as_posix().encode('utf-8') + b'\0')
                    digest.update(str(file.stat().st_size).encode() + b'\0')
                    with file.open('rb') as stream:
                        while chunk := stream.read(1024 * 1024):digest.update(chunk)
            packages=sorted(path for path in content.rglob('*') if path.is_file() and path.suffix.lower()=='.lpk')
            if packages:
                from .lpk_engine import REVISION,unpack_lpk
                digest.update(REVISION.encode())
            target=self.root/digest.hexdigest()[:32]
            cached=self.indexed(target)
            if cached:
                try:
                    for model in cached:prepare_model(model,stage/'validation')
                except (OSError,ValueError,KeyError,TypeError,AttributeError):
                    cached=[]
                else:
                    progress('ready','模型已导入过，已复用历史模型及其配置')
                    return [str(path) for path in cached]
            for index,package in enumerate(packages):
                unpack_lpk(package,content/'.kira-unpacked'/str(index),self.root.parent,progress)
            progress('validating','正在识别并检查解包后的模型资源…' if packages else '正在检查模型资源…')
            from .model_profile import read_json
            candidates=[]
            for model in sorted(content.rglob('*.json')):
                try:data=read_json(model)
                except (ValueError,OSError):continue
                refs=data.get('FileReferences')
                if isinstance(refs,dict) and isinstance(refs.get('Moc'),str):candidates.append(model)
            if not candidates:
                raise ValueError('未找到可用的 Cubism 3 JSON 模型。LPK 请连同对应 config.json 一起导入；普通模型需包含完整资源')
            for model in candidates:prepare_model(model, stage / 'validation')
            if packages:
                output_files=list((content/'.kira-unpacked').rglob('*'))
                if sum(p.stat().st_size for p in output_files if p.is_file())>MAX_BYTES or sum(p.is_file() for p in output_files)>MAX_FILES:
                    raise ValueError('LPK 解包结果总计超过 512 MB 或 4096 个文件')
            relative_models=[model.relative_to(content).as_posix() for model in candidates]
            (content/'.kira-models.json').write_text(json.dumps({'version':1,'models':relative_models,
                'packages':[str(package.relative_to(content)) for package in packages]},ensure_ascii=False),encoding='utf-8')
            if target.exists():
                import uuid
                target.rename(self.root/(target.name+'-previous-'+uuid.uuid4().hex[:8]))
            content.rename(target)
            paths=[str(target/safe_relative(name)) for name in relative_models]
            progress('ready','LPK 已解包并保留原包，模型已加入列表' if packages else '模型已导入')
            return paths
