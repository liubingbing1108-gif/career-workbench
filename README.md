# 求职空间 · Career Workbench

一个在本机运行的求职资料、投递管理和招聘表单辅助填写项目。个人资料保存在本机；Agent 理解官网问题，Chrome 扩展执行已确认的材料，填写后回读并核对草稿保存。**最终提交由本人完成。**

当前为 **v0.1.0 初步版本**，适合个人使用、开发与 Agent 集成。已有完整工作流与自动测试，但尚未覆盖所有招聘网站或跨平台真实申请，不承诺零错误、整表一分钟或无人值守投递。

## 使用路径

1. **我的资料**：手动维护或导入简历；教育、实习等按记录组织，每个字段可有多个版本，附件原件单独保存。
2. **投递管理**：输入链接或公司／岗位描述，预览并确认录入。已明确公司和岗位时直接生成预览；网页受限时保留链接，可补充信息后录入。只管理明确准备投递及已投递的岗位。
3. 行内点击 **开始投递**：进入二级工作台，区分直接申请表和资讯等来源，优先核验指定官网具体岗位，自动连接插件读取表单。
4. 左侧决定实习组合、版本、附件和实际缺项；右侧预览全部填写内容。一次确认后插件填写、上传和回读，支持暂存的官网再核对草稿。
5. 查看实际进度与待处理事项，点击 **去官网确认**，本人检查、处理协议并提交，再手动标记已投递。无草稿且重开会丢失的官网须保留当前页面。

正常流程复用同一岗位的官网标签页，无需逐次点插件。首次安装需加载扩展并授予 HTTPS 页面权限。

## 快速开始

需要 Python 3.11+、Google Chrome，以及已配置的语义 Agent。开发测试另需 Node.js 22+。macOS 是当前真实使用环境；Linux CI 检查离线逻辑和界面；Windows 的浏览器启动分支仍待实机验收。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/init_workbench.py
python scripts/start_workbench.py
```

Windows 使用 `py -m venv .venv` 和 `.venv\Scripts\Activate.ps1`，其余用 `python`。

新用户初始化建立空资料库，**发现任何已有资料目录即拒绝覆盖**。已有用户直接启动，不重复初始化。打开 [本机工作台](http://127.0.0.1:8768/)，按 [安装指南](docs/SETUP.md) 加载 `prototypes/icbc-native-extension` 扩展。扩展没有构建步骤。

语义层默认使用本机已登录、兼容所需结构化输出参数的 Codex CLI，也可通过 `CAREER_AGENT_COMMAND` 接入自己的 Agent。参见 [Agent 接入](docs/AGENT_INTEGRATION.md)，该接口有输入／输出 JSON 契约、校验和虚构示例，不强制特定模型供应商。

## 能力与边界

| 能力 | 当前范围 |
|---|---|
| 资料和版本 | 本机 SQLite；多记录、多版本、增量导入、仅本次编辑、原件 |
| 管理 | 一行一岗，来源／官网链接分开，人工状态、招聘进度、日期、删除 |
| 模型 | 简历结构提取、网站问题与完整经历集合匹配、公开官网检索 |
| 控件 | 原生输入及部分 Phoenix、Ant、Sugar 等控件，另有专用适配器 |
| 保存 | 已支持网站的暂存反馈＋重新打开同页核对；不支持时明确报告 |
| 执行 | 保护已有值、重复请求去重、取消、部分失败、原页进度、本人接手 |
| 尚待完善 | 任意网站完整覆盖、复杂分支／iframe、官网进度查询、个人中心批量导入、长期恢复、实时画面 |

附件完成、填写回读、草稿持久保存分别报告。网页变化、未支持控件或资料歧义会暂停，不能以“输入框非空”代表正确或已保存。

## 开发与交接

```sh
python -m pip install -r requirements-dev.lock
npm ci
npx playwright install chromium
python scripts/run_tests.py --ui
python scripts/check_docs.py
```

默认测试只用虚构资料、临时数据库和本机页面，不调用真实模型或招聘官网。初步版插件包 **1.3.2**，注入核心 **1.2.21**，客户端 **1.2.10**，执行协议 **v1**；各组件独立版本见 [扩展接口](prototypes/icbc-native-extension/API.md)。

- [项目交接](docs/HANDOFF_CONTEXT.md) · [当前产品规则](docs/PRODUCT_REQUIREMENTS.md)
- [架构](docs/ARCHITECTURE.md) · [数据与接口](docs/DATA_AND_API.md)
- [运行与恢复](docs/OPERATIONS.md) · [测试](docs/TESTING.md) · [路线](docs/ROADMAP.md)
- [贡献](CONTRIBUTING.md) · [隐私与安全](SECURITY.md) · [发布](docs/RELEASE.md)

运行资料、原件、申请 URL、截图、凭据和历史聊天不属于源码分发。请勿把服务暴露到公网；本版本为单用户本机应用。
