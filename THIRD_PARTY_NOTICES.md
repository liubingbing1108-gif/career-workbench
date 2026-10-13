# 第三方依赖

项目未内嵌第三方付费浏览器插件。浏览器原生 API 和招聘平台 DOM 类名用于互操作；历史调研材料不随源码分发。

直接运行依赖：pypdf（BSD-3-Clause）、jsonschema（MIT）。开发依赖：ReportLab（BSD）、python-docx（MIT）、Playwright（Apache-2.0）。它们由包管理器安装，许可证以已安装包和上游发行文件为准；传递依赖同样保留各自许可。Node 完整依赖版本见 package-lock.json，Python 直接依赖见 requirements 文件，已验证开发环境的完整版本见 requirements-dev.lock。

Codex CLI 或其他 Agent、Chrome 浏览器需用户另行安装，其账号、服务条款及费用由使用者自行配置。本仓库不重新分发这些客户端、模型或凭据。

本项目源码当前尚未选择开源许可证；不得将依赖许可证视为整个项目已采用同一许可证。
