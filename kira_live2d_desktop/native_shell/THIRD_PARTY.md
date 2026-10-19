# 原生渲染组件

原生壳使用 live2d-py 1.0.0（MIT）、PySide6 Essentials 6.10.2（Qt for Python，依其附带许可）、PyOpenGL 3.1.10。组件通过独立 Python 环境按需安装，安装包保留各自的许可文件。Live2D Cubism Core 和模型资源另有其自身条款；插件不改变模型授权。

## live2d-py

MIT License

Copyright (c) 2024 Arkueid

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## 可选 LPK 解包组件

首次导入 LPK 时单独下载 [ihopenot/LpkUnpacker](https://github.com/ihopenot/LpkUnpacker) 的固定修订 `906d4cdd5597403ebf46dde8fb47d9c81a352d19`（LpkUnpacker.py、Core/lpk_loader.py、Core/utils.py），以及 filetype 1.2.0 wheel。插件包不包含这些第三方文件；下载地址与 SHA-256 校验记录在 lpk_engine.py。工具在独立子进程中执行，不使用其 GUI；原始模型包另行保留。
