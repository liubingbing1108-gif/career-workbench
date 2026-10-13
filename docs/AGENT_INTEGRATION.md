# 接入自己的 Agent

上层 Agent 负责理解问题和证据，程序验证资料引用、范围、类型和转换；Chrome 扩展执行确认后的结构化材料。更换 Agent 不更换资料库或执行器，不允许模型直接绕过材料预览、协议或最终本人提交。

## 方式一：现有 Codex 适配器

默认从 PATH 查找 `codex`，也可用 `PROFILE_CODEX_BIN` 指定绝对路径。macOS 保留桌面版 CLI 的标准安装路径回退。需要本人已登录的兼容 CLI；调用参数见 `prototypes/profile-lab/recognizer.py`。不同发行版可能不支持所需参数，此时改用下面的命令适配方式，不声称任何 Codex 版本都兼容。

资料识别调用禁用工具，临时工作目录和结构化输出约束；官网搜索仅用公开搜索／打开页面。资料可能发送至当前模型服务商，原件保存在本机。仓库不含账号、密钥或登录态。

## 方式二：JSON 命令适配器

设置 `CAREER_AGENT_COMMAND` 为 **JSON 参数数组**，首项为可执行文件；脚本使用绝对路径。通过 stdin 接收一个 UTF-8 JSON 请求，stdout 只返回一个 JSON 对象。不要把诊断、Token、提示词和个人资料打印到 stdout；适配器错误不会回显底层 stderr。

```sh
export CAREER_AGENT_COMMAND='["/absolute/path/to/python", "/absolute/path/to/my_agent.py"]'
# 仅在了解并同意自选 Agent 的资料处理方式后设置：
export CAREER_AGENT_ALLOW_PERSONAL_DATA=1
python scripts/start_workbench.py
```

不要提交本地环境文件。自定义命令由用户自己安装和信任，进程不是安全沙箱；`capabilities` 是集成约束，需要你的包装器落实。不要让文档或网页内容成为工具指令，不要赋予自动化最终提交能力。没有显式配置不会切换到第三方模型。

请求：

```json
{
  "protocol_version": 1,
  "task": "structured_inference",
  "instructions": "任务专用约束",
  "prompt": "包含待处理数据的任务提示",
  "output_schema": {"type":"object","properties":{"value":{"type":"string"}},"required":["value"],"additionalProperties":false},
  "capabilities": {"public_web":false,"shell":false,"files":false,"browser_actions":false}
}
```

响应：

```json
{"protocol_version":1,"result":{"value":"虚构示例"},"usage":{}}
```

`result` 必须严格符合每次请求的 `output_schema`。提取任务还要能在原始文档块核对证据；映射任务必须引用当前字段和正确记录。格式校验不能替代语义准确性。

公开官网任务 `task=public_lookup`，`capabilities.public_web=true`。只传公开公司／岗位身份及来源线索，不传简历或联系方式。需真实执行搜索和打开页面，并返回顶层 `web_pages`：

```json
{"protocol_version":1,"result":{"company_url":"https://example.com","recruitment_url":"https://example.com/jobs","candidates":[],"message":"示例"},"web_pages":[{"url":"https://example.com/jobs","title":"示例招聘","snippet":"实际读到的原文证据","opened":true}]}
```

这是虚构协议示例，不是实际官网核验结果。`opened=true` 必须来自工具执行回执，不能由模型猜造。没有打开证据直接拒绝；后端继续核对官网授权链、岗位名称、地点与支持平台的公开职位 API。实现见 `official.py`、`public_jobs.py`。不支持检索的 Agent 应报失败，而不是编网址。

[虚构回声示例](../examples/agent_echo.py) 可用于联调管道；它仅支持演示 schema，无法解析真实简历或搜索官网，不能用它进行真实申请。

## 执行器接口与二次开发

[执行协议](../prototypes/icbc-native-extension/API.md) 和 [TypeScript 契约](../prototypes/icbc-native-extension/protocol.d.ts) 是唯一填写接口。模型返回字段映射和资料引用，服务器编译用户确认的材料，执行器扫描／预检查／新增记录／填写／回读／停止。没有任意脚本、任意选择器、任意点击或最终提交接口。

若让编码 Agent 维护本项目，从 [AGENTS.md](../AGENTS.md) 和 [交接](HANDOFF_CONTEXT.md) 开始；使用虚构夹具，不读取或发布 `.runtime`，不因任务名包含“投递”就自动提交。
