from pathlib import Path
import zipfile
import json

base = Path(__file__).resolve().parents[1]
root = base if (base / 'manifest.json').is_file() else base / 'kira_live2d_desktop'
manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
target = base / 'dist' / (manifest['plugin_id'] + '-' + manifest['version'] + '.zip')
target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if path.is_file() and not any(part in {'__pycache__', 'tests', '.git', 'dist', 'tools'} for part in relative.parts):
            archive.write(path, manifest['plugin_id'] + '/' + relative.as_posix())
print(target)
