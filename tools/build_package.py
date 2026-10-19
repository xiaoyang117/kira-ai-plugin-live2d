from pathlib import Path
import zipfile
import json
base = Path(__file__).resolve().parents[1]
root = base / 'kira_live2d_desktop'
version = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))['version']
target = base / 'dist' / f'kira_live2d_desktop-{version}.zip'
target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and 'tests' not in path.parts:
            archive.write(path, path.relative_to(base).as_posix())
print(target)
