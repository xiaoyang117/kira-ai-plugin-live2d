"""Build the KiraAI-independent Windows shell distribution."""
import json
from pathlib import Path
import zipfile
import uuid

def build_remote_package(folder,force=False):
    root=Path(__file__).parent;version=json.loads((root/'manifest.json').read_text(encoding='utf-8'))['version']
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);target=folder/f'Kira-Live2D-Remote-{version}.zip'
    if target.is_file() and not force:return target
    temporary=target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    names=('window.py','behavior.py','part_motion.py','speech_bubble.py','win_input.py','remote_model.py','remote_runner.py','socket_wire.py','glass_theme.py')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in names:archive.write(root/'native_shell'/name,'shell/'+name)
        for file in (root/'native_shell/icons').glob('*'):archive.write(file,'shell/icons/'+file.name)
        for file in (root/'remote_shell').glob('*'):
            if file.is_file():archive.write(file,file.name)
        archive.write(root/'native_shell/THIRD_PARTY.md','THIRD_PARTY.md')
        archive.write(root/'native_shell/WEBSOCKET-LICENSE.txt','WEBSOCKET-LICENSE.txt')
    temporary.replace(target);return target
