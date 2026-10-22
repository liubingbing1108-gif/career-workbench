# 从这里开始

使用者先读 [README](README.md) 与 [安装](docs/SETUP.md)。自己的 Agent 接入方式见 [协议](docs/AGENT_INTEGRATION.md)。

开发或接续按顺序读 [协作规则](AGENTS.md)、[产品规则](docs/PRODUCT_REQUIREMENTS.md)、[交接](docs/HANDOFF_CONTEXT.md)、[架构](docs/ARCHITECTURE.md)、[测试](docs/TESTING.md)。

本仓库是MIT 开源预览版，不包含创建者的资料库或真实申请现场。不要尝试从历史用例猜测个人资料。运行初始化只会建立当前使用者的空库。


项目维护先读[GOVERNANCE](GOVERNANCE.md)，按[能力清单](docs/CAPABILITIES.json)定位源码、测试和限制，再按[Agent手册](docs/AGENT_PLAYBOOK.md)接续。每次修改用独立变更片段记录，不能依赖创建者的聊天。

## 每次开发接续

先运行`python scripts/project_handoff.py status`并阅读[自动接续索引](docs/PROJECT_ACTIVITY.md)；按[接续机制](docs/CONTINUITY.md)登记范围、记录结果并同步项目管理。每次修改和恢复均由Agent执行，无需用户重复提醒。
