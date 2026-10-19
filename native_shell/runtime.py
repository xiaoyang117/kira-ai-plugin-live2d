"""Separate native runtime; no Qt or Cubism imports in the KiraAI process."""
import os
from pathlib import Path
import subprocess
import sys
import venv

PACKAGES = ['live2d-py==1.0.0','PySide6-Essentials==6.10.2','PyOpenGL==3.1.10','websocket-client==1.8.0']

def ensure_runtime(data_dir):
    root = Path(data_dir)/'native-runtime-v1'
    python = root/'Scripts'/'python.exe'
    marker = root/'ready.txt'
    if python.is_file() and marker.is_file() and marker.read_text() == '\n'.join(PACKAGES):
        return python
    if sys.platform != 'win32':
        raise ValueError('独立壳目前支持 Windows 64 位')
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(root)
    log = root/'install.log'
    with log.open('wb') as output:
        result = subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check',
            '--only-binary=:all:',*PACKAGES],stdout=output,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,timeout=600)
    if result.returncode:
        raise RuntimeError('独立壳组件安装失败，请检查 '+str(log))
    marker.write_text('\n'.join(PACKAGES))
    return python
