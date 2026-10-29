# 显式加载、兼容与验收

本包已在候选产品契约30中显式加载并通过虚构请求适配、缺包拒绝、关系落库重启复用及停用测试；活动产品尚未切换。候选源码已提供组合确认、用户选定最小片段后请求摘取、关联语言/考试混合行投影，以及新定义/答案/明确勾选关系同事务回库，并通过虚构适配器及材料页面测试。字段合并重定向与关系纠正管理界面仍待完成，真实模型/官网未验收。下表保留原接入设计，不能把设计项当成已全部完成。

## 当前可复用接点

| 接点（相对产品根） | 已有行为 | 本包接入所需工作 |
|---|---|---|
| prototypes/profile-lab/mapping.py：WebsiteMapper.map / mapping_schema | 程序内长提示词、旧三状态 mapped/new/ambiguous、contract_version=2；混合 DOM 区块可拆分后第二次理解 | 显式加载本包，保留真实扫描上下文、叶节点覆盖与组关联；新增响应适配，不能把新状态直接传旧 schema |
| prototypes/profile-lab/recognizer.py：CodexRecognizer.call | 临时 cwd、project_doc_max_bytes=0、skills.include_instructions=false，禁工具；自定义 Agent 走同一 call_agent | 保持隔离，不重新打开所有 Skills；规则由父程序读入 prompt，无工具查询伪装 |
| prototypes/profile-lab/resume_skill.py：catalog / rules | catalog 沿用 id/label/category/type/aliases/record_types/entry_id/group/widget；rules 显式加载解析规则并记录 SHA | 共用字段来源/身份；仅作接入参考，不能把解析侧规则替换为本包，也不复制静态字段表 |
| prototypes/profile-lab/profile_hierarchy.py：mapping_fields | 提供当前层级和局部记录字段上下文 | 复用目录投影，补 meaning、单位/尺度与修订；未知元数据显式报告，不能从中文展示名强推类型 |
| prototypes/profile-lab/application.py：scan / install_mapping / website_value | 核验覆盖、category、已有 ID、requirement、transform；保存 session mapping；兼容 new 等旧逻辑 | 新契约先独立校验，阻止未知变 new 的回退；新增查询/排除/修订保护；原取值/预览服务继续承担答案 |
| prototypes/profile-lab/requirements.py：validate_requirement / resolve_set | 校验条件字段，按范围/排序/条数取完整对象集合 | 保留原语义，适配 selector，不以 DOM 行替代对象；增加子类型/局部 entry_id 一致性 |
| prototypes/profile-lab/profile_group_versions.py、material_sets.py、preparation.py | 当前整组版本、材料选择与草稿 | 共用同一版本目录，生成本机 availability_checks，写前复验；P29/P30 尚待实施的接口不可假定已具备 |
| 现有 lab 持久化层 | 活动资料与会话在既有库 | 按 service.md 实施关系事务、查询和排除；本包没有迁移或另一套数据库 |

## 加载协议

唯一源 `skills/application-field-mapper/`。`manifest.json` 指定 package/rules_version/contract_version、所有受控文件 SHA-256，以及 runtime_files。模型只加载 runtime_files 的 Markdown（SKILL、决策表、模型契约），并单独接收 schema 的 response 结构；service/integration、测试和验收报告不塞进模型提示词。

`scripts/validate.py` 的 load_bundle(root, expected_digest) 是离线可用参考：校验 manifest 结构/版本、路径与符号链接、清单完整性和每个文件的 SHA；摘要为 manifest canonical JSON 的 SHA-256，返回 rules/schema/digest。expected_digest 必须由**产品配置/受审发布版本**提供；与包放在一起的 manifest 自校验只防损坏，不是独立信任根。不能把现场读取的摘要原样作为期望值来假装 pin 验证。

产品步骤：

构建 response schema 时保留 `$defs`（例如 `{**schema, '$ref': '#/$defs/response'}`）；不能只摘出内层对象导致引用失效。特定模型适配器若不支持该 JSON Schema 形态，由产品适配器解析/内联引用并验收，不能假称现有 CLI 已测试支持。

1. 部署选择被支持的规则版本/契约与 pin；在发模型请求前加载并校验，缺文件、非 UTF-8、未列文件、路径越界、未知契约或 pin 不符返回 skill_unavailable。不得静默使用旧硬编码 prompt。既有已校验关系可继续形成独立预览，未知项明确不可用。
2. 每次准备 query 最新目录/关系/排除；确定可复用项无需重调模型。剩余问题构造 request，调用同一 CodexRecognizer.call，purpose 改为网站字段候选理解，web_search=false；自定义 Agent 同样收到规则和 response schema。
3. request 的规则信封由程序记录 rules_version、contract_version、bundle_sha256 和 request_id/context；模型输出不负责证明规则被加载。传输日志只记版本/摘要、耗时、错误码及计数，不默认记录个人答案或原文。产品集成测试捕获实际 call 的 prompt/schema，核对与已校验 bundle 相同。
4. Schema＋跨引用验证后调用原目录/范围/版本/取值检查；从已有资料取值再预览。确认关系与资料回库严格分离，P32按当前已确认的选中差异原子回库规则交接。模型字符串不执行，也不提供 SQL/脚本/任意选择器。
5. 将规则/目录/关系/扫描及对象版本修订记录在准备任务，执行前复验依赖；已确认历史快照不回算。规则升级不自动新增/批准关系、不批量重解析资料。兼容补丁只对新准备生效；影响旧判断时将受影响关系置待复核，保留草稿。破坏结构变更须新契约主版本和迁移验收。

## 旧输出兼容策略（待实施）

等价单字段、受支持格式转换且 selector 能完整表示时，可转换为旧 mapped 及其 requirement。旧 mapped 只是语义引用成功，不等于答案 ready。compose、extract、partial、未决新属性与新子类型不能丢掉信息后假装 mapped；保留新结构并在旧 UI 处标相关项待处理。new_attribute_candidate 不能直接送入旧 new 创建/保存分支。新 v1 与现行映射整数2属于不同命名空间，禁止数值大小比较。

混合 DOM 区块拆开是扫描归组处理，extract_candidate 是从资料长文取片段，两者不可混同。保留网站原始 id→叶节点 id 的本次映射，父 children 每项恰好覆盖；再次拆分仍不确定就失败，不能漏掉选填项。已确认对象、草稿及历史材料的旧引用读取通过现有兼容服务适配，不建立两套可写目录。

## 验收分层

本包命令（产品根目录）：

```sh
python3 skills/application-field-mapper/scripts/validate.py --self-test
python3 skills/application-field-mapper/scripts/validate.py --check fixtures/conformance.json
python3 skills/application-field-mapper/scripts/validate.py --check fixtures/rejections.json
```

`--check` 路径相对本包；可传绝对路径测试其他**虚构** JSON 输入输出配对。conformance 包含15项候选的完整请求/响应；rejections 对该虚构基线独立施加12个错误变体，要求逐个返回指定拒绝码。其余生命周期负例在 test_contract.py。运行依赖 Python 3.11+ 与现有开发依赖 jsonschema；结构校验另按 skill-creator 的 quick_validate.py 执行（需 PyYAML）。脚本不安装依赖、不联网、不调用模型、不访问 .runtime、不输出个人正文。测试断言正例接受、负例拒绝和纯函数返回结果，不能当作真实模型前向测试。

后续产品接入需独立补：实际 prompt/schema 注入与缺包拒绝；旧三状态兼容；同库关系保存后进程重启查询；并发事务/失败回滚/幂等重放；纠错停用及字段合并排除迁移；本次草稿和历史快照保护；虚构隔离 UI 的局部决策/预览。真实模型测试只发送另行授权的虚构样例，真实官网需届时明确范围。离线通过不代表以上接入或部署完成。
