# KiraAI 原生 Live2D 桌宠插件

适用于 **KiraAI 3.0** 的原生 Live2D 桌宠插件，当前版本 **0.24.4**。

独立连接端源码和安装包另见 [kira-live2d-client](https://github.com/xiaoyang117/kira-live2d-client)。

## 安装

从 [Releases](https://github.com/xiaoyang117/kiraai-live2d-desktop/releases/latest) 下载 `kira_live2d_desktop-0.24.4.zip`，在 KiraAI 插件管理中安装、启用，进入「Live2D 桌宠」配置。

首次安装默认不启动壳，请导入有权使用的模型，再手动选择：

- **本机桌宠**：插件启动本机原生渲染壳。
- **远程壳**：插件提供连接服务，Windows / 安卓连接端主动连接运行 KiraAI 的电脑，填写电脑地址、端口和访问密钥；同一时间支持一个远程壳。
- **不启动**：不启动渲染进程。

Windows 独立端和安卓 APK 在 [连接端 Releases](https://github.com/xiaoyang117/kira-live2d-client/releases/latest) 下载。

## 功能

- 原生 Cubism 模型显示、透明桌宠、鼠标追踪、可视调试、点击与拖动互动。
- 自动读取表情、动作和用途建议；支持改名、禁用、预览、换装和按模型保存配置。
- 独立动作 Agent 读取当前人设、用户输入、交互事件和历史上下文，与主 LLM 并行工作，不等待或接收本轮主 LLM 输出；文字回复不等待动作决策。
- 桌面输入与 KiraAI 网页聊天联动，历史由 KiraAI 保存；可选独立会话或网页聊天会话。
- WebSocket 通信、语音音量口型、无语音时的简易文字口型、回复气泡和可选屏幕互动。
- LPK / WPK 导入按需下载解包组件，支持生成 AI 控制副本并保留原始模型。

## 文档与源码

- [详细使用教程](kira_live2d_desktop/使用教程.md)
- [版本记录与插件说明](kira_live2d_desktop/README.md)
- 打包插件：`python tools/build_package.py`，输出至 `dist/`。
- `native_shell/` 与 `remote_shell/` 保留插件所需的原生壳与按需打包逻辑；可单独使用的连接端在另一仓库维护。
- Python 回归测试位于 `kira_live2d_desktop/tests`，依赖 KiraAI 本体环境。部分测试保留开发机路径并使用未分发的模型样本，目前尚未改为通用 CI。

## 模型与第三方组件

支持 KiraAI `>=3.0.0,<4.0.0`、Cubism 3 及以上模型资源。仓库和发布包不附带个人模型、聊天记录、密钥、签名私钥或开发缓存。请自行准备有权使用的模型。

原生组件和解包工具适用各自许可，参见 [第三方组件说明](kira_live2d_desktop/native_shell/THIRD_PARTY.md)。
