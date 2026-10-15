# 第三方依赖

本项目采用[MIT](LICENSE)。不内嵌受限第三方浏览器插件、浏览器、模型客户端或模型权重。招聘平台DOM类名只用于互操作，私人调研材料不分发。

直接运行依赖：MarkItDown（MIT）、pypdf（BSD-3-Clause）、jsonschema（MIT）、tzdata（Apache-2.0，IANA 时区数据为公共领域）。开发依赖：ReportLab（BSD）、python-docx（MIT）、Playwright（Apache-2.0）。由包管理器安装，传递依赖分别保留其发行许可；Python依赖见requirements文件，Node见package-lock.json。源码ZIP不捆绑依赖二进制。

MarkItDown会安装文档解析、格式识别等传递依赖；开发锁用于Python3.12+，运行依赖由Python3.11+解析兼容版本。安装后可用pip show查看包许可证与上游信息。

Codex或自选Agent和Chrome需使用者另行安装、登录，其服务条款及费用由使用者自行配置。本仓库不重新分发账号、密钥或登录态。
