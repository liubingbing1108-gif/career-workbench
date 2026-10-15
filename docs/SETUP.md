# 安装与首次运行

## 环境

Python 3.11+、Google Chrome。Node.js 22+ 仅用于测试。生产前端是原生 HTML/CSS/JS，无需 Node 构建。

优先使用 README 的 `python3 scripts/bootstrap.py`（Windows用`py -3`）安装命令。激活同一环境后运行初始化和启动器；启动器优先使用已激活的 Python 虚拟环境；仅未激活环境且本机已有桌面捆绑 Python 时兼容该旧安装，其他机器不需要该运行时。文档统一由 MarkItDown 转换，pypdf仅作PDF输入检查；不包含扫描件OCR。

## 初始化

`python scripts/init_workbench.py` 只用于新安装。它创建 `.runtime/profile/lab.sqlite`、`.runtime/management/management.sqlite3` 和相对路径配置。包含空字段与分类，不包含任何人的简历、经历或岗位。

重复初始化会拒绝；资料目录存在但配置丢失也拒绝。此时按 [恢复文档](OPERATIONS.md) 处理，不删除目录再重建。

`python scripts/start_workbench.py` 启动到 `http://127.0.0.1:8768/`。重复启动复用现有本机实例，同一电脑只运行一个实例。不要在填写期间重启。macOS/Linux 可用 `--restart`，Windows 请关闭原 Python 服务后重启。日志在 `.runtime/`，不要公开分享。

## Chrome 扩展

1. 在 Chrome 扩展管理启用开发者模式，选择“加载已解压的扩展程序”。
2. 选项目中的 `prototypes/icbc-native-extension` 文件夹。
3. 在 Chrome 中打开本机工作台，录入岗位后点击开始投递；首次提示时点击“授权并启用自动填写”，授予 HTTPS 页面权限。
4. 后续从工作台开始，插件自动连接，无需每次打开工具栏。登录、验证码和协议由本人处理。

升级源码后，在扩展管理中重新加载扩展，再只刷新本机工作台；没有草稿保存入口的官网表单不要刷新。包版本、核心版本和客户端版本不同是独立版本号，不能仅凭文件修改判断浏览器已加载新版。更新后先用虚构表单回归，真实申请按回读结果检查。不会自动扩大权限。

推荐直接用 Chrome 打开工作台。其他浏览器通过短效中转页交给 Chrome，中转页完成后关闭。Linux/Windows 未找到 Chrome 时设置 `CAREER_CHROME_BIN` 为 Chrome 可执行文件的绝对路径。

## Agent

见 [Agent 接入](AGENT_INTEGRATION.md)。先确认自己的模型账号与资料处理政策，再导入真实简历。没有 Agent 时仍可手动维护资料与管理记录；自动解析和语义匹配会提示未配置，不假装完成。

## 常见问题

- 找不到官网：核对公司、具体岗位、地点；资讯链接只是线索。搜索 Agent 必须能返回实际打开的官方页面证据。
- 扩展未连接：检查扩展已加载、HTTPS 权限、本机端口、工作台刷新。不要重复创建多个官网页。
- 无法保存：查看具体字段和官网必填反馈；只有重新打开仍匹配才显示已保存。
- PDF 无文字：暂不支持扫描件 OCR，可手动维护资料。
- 日期只知道月份：保持月精度；官网要求具体日时由本人提供，不自动补日。
- 网络证书错误：修复当前 Python 的 CA 信任配置；不要关闭 TLS 验证。

## 安装诊断

在虚拟环境中运行 `python scripts/doctor.py`。检查Python、依赖、既有数据库位置、Chrome与Agent命令，输出不包含凭据和个人答案，不调用模型。WARN表示对应可选能力尚未配置，ERROR应先修复；诊断通过不能代替官网兼容或模型联网验证。

手动安装仍可使用 `python -m venv .venv`、安装requirements.txt、init_workbench.py、start_workbench.py。开发完整锁需要Python3.12+；普通使用支持Python3.11+，由requirements.txt解析兼容依赖。
