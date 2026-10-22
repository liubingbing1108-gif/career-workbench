# 参与开发

先读 [产品规则](docs/PRODUCT_REQUIREMENTS.md)、[架构](docs/ARCHITECTURE.md) 和 [交接](docs/HANDOFF_CONTEXT.md)。保持“我的资料／投递管理”两个主入口，复用当前本机服务和执行协议，避免另一套资料库或执行器。

提交只包含源码、通用文档和虚构夹具。安装开发依赖，运行 `python scripts/run_tests.py --ui`、`python scripts/check_docs.py`。新控件驱动需覆盖实际输入提交、回读、已有值保护、错误和取消；涉及保存必须包含重新打开后的验证，不能只测字符串被写入。

PR 描述说明具体问题、修改后的行为、测试及未覆盖边界。文档与实现同轮更新。真实官网测试必须由测试者授权，使用本人确认材料，最终本人提交；不要把生产数据混入公共测试。

依赖变更更新锁文件及许可证记录。不要提交第三方付费插件或来源不明代码。历史模块名含 lab 是目录兼容性，不是另一个产品入口。


统一协作规则见[GOVERNANCE](GOVERNANCE.md)。新增`.changes/<UTC时间>-<主题>.json`并运行`python scripts/check_project.py --base <完整PR基线SHA>`；CI会检查整个PR的变更覆盖。未发布片段通过`python scripts/check_project.py --notes`汇总，不让每个贡献者竞争修改同一段CHANGELOG。能力索引和Agent接续路径见[手册](docs/AGENT_PLAYBOOK.md)。

## 自动交接

按[CONTINUITY](docs/CONTINUITY.md)执行begin/record，自动生成[更新索引](docs/PROJECT_ACTIVITY.md)。测试入口与CI会拒绝缺少接续元数据或索引过期；PR必须保留完整变更覆盖。
