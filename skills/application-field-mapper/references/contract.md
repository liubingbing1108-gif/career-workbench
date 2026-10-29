# 模型输入输出契约 v1

状态：本包的工程契约，未接入活动产品。唯一机器结构是 [contract.schema.json](../schemas/contract.schema.json)，使用 Draft 2020-12；根是 request，`$defs.response` 是模型输出。额外属性一律拒绝。JSON Schema 验结构，脚本校验跨引用；语义本身仍需模型和产品检查，不能由 Schema 证明。

## 输入 request

| 字段 | 提供者与含义 |
|---|---|
| contract_version / request_id | 固定契约名；本次调用标识 |
| context | 本岗位 preparation_id、session_id、target_revision、catalog_revision、profile_revision、relation_revision、scan_revision；不可跨岗位重用，profile_revision 绑定答案事实与对象/版本目录的当前修订 |
| site | 规范 HTTPS origin、显式 tenant（无租户也用明确标识，未知用空串）、表单家族 form_key；不传申请人 URL、token、cookie |
| questions | 程序将可填写叶节点展平，保留唯一 id、group_id、label/section/instructions/examples/control/options/condition、required、长度口径、对象上下文和语义指纹；父集合只作上下文，不变成重复问题 |
| catalog | 当前目录的 `id,label,category,type,aliases,record_types,entry_id`；附本次 `meaning,unit,scale,revision` 元数据。id 原样沿用解析侧；这是按需投影，不是新增字段目录 |
| search | 检索回执 receipt、catalog_revision、complete_categories；只把真正查全的 category 列入，包含扩展与局部定义。空列表表示窄检索；模型不能自行改成查全 |
| relations / exclusions | 当前相关关系和排除项，包括非 active 状态；由程序先查询和筛选。不能仅返回正例而隐藏纠错记录 |
| availability_checks | 可选的本机检查回执，绑定 question_id、来源字段列表、对象/版本/修订和状态；无需发送答案正文。没有回执就 not_evaluated |
| source_spans | 仅拆分任务所必需、当前已授权的最小原文；绑定 field_id/entry_id/version_id/revision。普通映射留空 |

`question.object` 的 category/record_type 由已知分区上下文提供；不确定用空串，模型可提出明确类别但程序须复核。`entry_id` 只用于已绑定的局部对象；不能因数据为空改变类型。网站字段 ID 只在本扫描内有意义；跨扫描持久关系靠受约束语义键，不靠 DOM 序号。

`selector` 沿用现有 requirement 的 selection、filters、rank 含义：filters 全部 AND，字段必须属于当前对象；domain/op 取现有 requirements 支持的集合。`entry_ids` 只允许显式给定对象；不是让模型从记忆创造记录。`required_values/min_items/max_items` 保留网站完整性要求。selector=null 仅表示本次问题绑定的非重复单项；重复问题必须给 selector。group_id 是本次组标识，不替代对象身份。同一语义来源组的问题必须用同一 category/record_type/selector；混合网页行的能力和考试拆成不同语义来源组，网页行关联由产品保留。对象未知时由输出提出类型和selector，产品按真实类型复核。

## 输出 response

回显 contract_version、request_id、context；`decisions` 对输入每个叶节点恰好一项，含选填项。响应不得包含答案或写入动作。

- `proposal_state` 固定 candidate；semantic_status 取决策表枚举。
- `category/record_type`、`selector`：候选对象范围；不能越过输入已确定的归属。
- `sources`：现有 field_id 及其覆盖的题意部分。`alternatives`：未确定的候选字段列表与区分理由；无法识别时可以为空。
- `coverage`：covered/uncovered 原题意片段、partial；有未覆盖内容必须 ambiguous 或 unresolved，不能宣称 equivalent。组合全覆盖但实际某来源没值由 availability 表示。
- `plan`：kind、允许的 transform 和 `extracts`；extracts 指向 source_spans 的 start/end（0 起、右开、Python/Unicode code point），并解释用于题目哪一部分。不返回自行改写的事实值；程序从原文取出草稿核验。
- `availability`：status 与 check_id。ready/missing_value/version_needed/conflict 只能引用本次给定回执；extract_candidate 必须 draft_required；其他没有证据用 not_evaluated。这是模型转述，不是最终可执行判定。
- `relation_id`：可复用的 active 关系或 null；模型不能将候选关系变 active。组合/拆分用 recipe 关系，alias 仅一字段等价。
- `new_attribute`：只含 label/meaning/category/record_type/type/unit/scale/search_receipt；不能给新 ID、共享范围或默认值。必须明确归属且目录查全。
- `request_expand_catalog`：缺候选时请求程序查全。程序最多补查后再调用一次；仍未知交 unresolved，避免重复循环。
- `reason/clarification`：简短可核验依据和必要的具体问题；无歧义时 clarification 为空，不重复确认固定资料。

版本名字、默认标记或“有很多版本”不构成适用性证据。availability_checks 由同一版本服务按对象、整组版本、当前事实、网站语义和每项长度口径检查，不引入版本语言/岗位/公司属性，不能拼装不同版本。缺值不等于“无/否/0”，原文明确没有与未提供须由资料服务区分。

`exclusions.match=target` 禁用该上下文下的错误目标字段；`match=plan` 只禁用 field_ids＋selector＋plan 的错误组合，允许同一字段经明确纠正后采用正确筛选。两者都不能由模型撤销。摘取持久方案不带原文范围；每次范围只属于当前 source_spans，不能跨对象或版本拼接。

## 校验与失败

脚本提供结构、覆盖、对象、局部字段、筛选引用、排重回执、状态一致性、关系复用和摘取范围校验。它不证明自然语言同义、最高学历计算、计数口径或真实模型能力；服务需调用既有 requirements、材料/版本服务并在执行前复验。

输入不完整/不兼容返回程序错误 `contract_invalid`；坏输出返回 `candidate_invalid`，不入库。新请求/修订不符 `stale_context`；规则缺失/摘要不符 `skill_unavailable`。局部错误保留有效项与草稿，但不能将坏项降级成可执行的 `new`。错误恢复使用当前产品的有界重试，不自动发送更多资料或换供应商。
