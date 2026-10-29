# 关系服务与生命周期 v1

这是供现有产品实现的逻辑服务契约，不是已存在的 HTTP API，也不是新建数据库的迁移脚本。模型不能调用这些服务。Schema 的 query/query_result/update/update_result 为边界 DTO；离线脚本仅校验其约束，不保存业务数据。

## 每次准备都查询

`query(query) -> query_result`：每次读取表单、重准备、恢复准备和显式重试时，由现有准备服务从活动资料库同一一致性快照读取字段目录、关系和排除记录，返回最新 context 与 query_receipt。传入的 context 是调用方观测值；返回值代表查询时的版本，调用方采用新值构建请求，不把旧请求修订当成最新。不得只从聊天、前次模型输出、浏览器缓存或 Skill 文件恢复关系。

按本岗位目标、网站租户、表单家族、对象类型/子类型及局部 entry_id 限定范围。site 关系必须 origin、tenant、form_key 都相同；tenant 未知不能自动复用任何 site 关系。同一 ATS 不代表同一租户。general 关系必须显式确认过通用范围，origin/tenant/form_key 留空，仍受 category/record_type/entry_id 及语义指纹约束；模型不能把 site 提升 general。本站精确关系优先，但任何适用的相互矛盾 active 关系都返回冲突，不静默取优先级较高的一条。

`semantic_fingerprint` 由程序将 label、section、instructions、examples、control、options、condition、object 的 category/record_type/repeatable、unit、scale 以 UTF-8 canonical JSON（sort_keys=true，separators=(',', ':')，ensure_ascii=false）做 SHA-256；数组顺序保留，避免改变选项含义。排除瞬时 DOM id、group_id、具体对象 ID、URL、长度上限及答案。局部对象限制由 scope 单独保证。只允许逐字符串首尾去空白，不自行折叠语义；未知标签应重新判断，即使实际同义也不偷用旧关系。其他语义等价归一如后续需要，须独立版本化和验证，本 v1 不支持。

关系保存原问题名和必要上下文，但只存脱敏站点 origin/明确租户和表单家族，不保存申请者 URL 查询参数、会话令牌或答案。指纹不代替业务理解；它只判定上次确认的完整问题上下文是否改变。同义三个叫法有三条受约束关系，指向同一字段 ID，不产生三个资料字段。

查询返回 active 候选、待复核/停用/被替代关系及适用 exclusions。先处理排除，再判关系资格：状态 active、兼容契约、当前字段修订/作用域有效、完整问题指纹相同、范围一致才可复用。多个关系不同 target/selector/plan 时只返回冲突；一致目标可按同义引用去重。无命中时程序提供候选目录让模型理解；新属性前必须再查全所属类型（含受限局部定义、扩展与别名），产生新 search receipt。窄检索漏项不得成为新增依据。

`field_revisions` 必须完整覆盖 field_ids，每个字段仍有效；selector 中筛选/排序/required_values 引用也必须存在且同对象，执行前另核其当前修订。catalog_revision 绑定整个查询范围，可发现筛选字段变更。一条 alias 只能有一个字段，plan 为 alias/transform；compose/extract 必须 kind=recipe。recipe 不存个人文字、已选具体版本或原文片段偏移：split 只保留 extract 类型，实际片段每次从本次对象重新提议核验。

## 关系状态与确认依据

| 当前状态 | 事件与前提 | 新状态 |
|---|---|---|
| 不存在 / candidate | 用户在具体预览明确接受对应及范围；程序校验与排重通过 | active |
| active | 语义、单位、选项、字段含义/类型或依赖变化 | needs_review |
| active / needs_review / candidate | 用户停用 | disabled |
| active / needs_review / candidate | 用户纠正到新的候选；同事务记旧目标排除及新关系 | 旧关系 superseded，新关系 active |
| needs_review | 用户复核当前候选和范围 | active（新修订） |
| disabled / superseded | 普通模型建议、材料重放、旧确认 | 拒绝；不能自动复活 |

disabled/superseded 的恢复不在普通更新 API 中。未来若提供恢复，必须显式选择具体排除/旧关系，重新确认当前目标、范围和修订；本 v1 返回 rejected。错误关系纠正/停用时，程序创建不可被模型删除的 exclusion，记录原目标、selector/plan、上下文、作用域、修订及原因。错误字段用 match=target，禁止相同上下文下该目标；仅筛选/转换错误用 match=plan，禁止旧 field_ids＋selector＋plan，允许经确认的同字段正确方案。不能因纠正“学校”的取用范围而把学校字段整个禁用。exclusion 对符合条件的任何新 ID 候选同样生效，不能通过新建 relation_id 绕过；纠正后旧错误排除仍保留。更宽通用关系也不能覆盖本站的排除。原始表述改了导致指纹不同时仍需新语义评审，不能声称旧排除对所有未知同义词已完美覆盖。

确认依据为本次材料预览中明确接受的“网站问题→资料字段/方案＋对象与复用范围”，或次级关系管理入口的明确纠正/停用。现有适用关系直接复用，不增加日常逐项确认。总预览没有展示或明确接受某一新关系时，点击填写不能凭空当作该关系的确认。填写成功、官网保存、最终提交和模型高置信度均不是语义确认。confirmation_id、basis、confirmed_at 由程序从实际操作生成，不能信任模型自报。

## 原子更新与并发

`update(update) -> update_result` 由现有资料持久化事务承载，无新端口或执行器。operation=confirm/correct/reconfirm 需 confirmation_id 与具体 basis；disable 也需用户操作凭据；invalidate 可由依赖变更产生，须可回溯事件 reason。candidate 为待存候选 DTO，确认后由服务生成 active 状态、时间与新修订，不能直接信任其自报状态。

1. 在服务验证调用来源/授权范围、请求结构和 payload_sha256。摘要由 update 去掉 payload_sha256 后按上述 canonical JSON 计算，不能由模型提供。
2. 事务内先按 idempotency_key 查询已提交回执。同 key 同摘要返回原结果的 replayed，不重做写入，即使当前状态已更正；revision 保留原回执修订，current_revision/current_state 返回当前关系状态，不能把旧 active 结果再次投入执行。同 key 不同摘要返回 idempotency_conflict。
3. 无回执时，核对 expected_context、relation_id 的 expected_revision（不存在为0），重新检查当前 catalog、active 关系和 exclusions。任何修订变更返回 stale_context / revision_conflict；不覆盖用户并发纠正，保留草稿并重新查询。
4. 事务中按 scope＋semantic_fingerprint＋kind＋field_ids＋selector＋plan 规范键排重；同目标重复确认复用一个关系，不同目标同上下文返回 relation_conflict。不能仅靠模型调用前的查询；数据库唯一约束/事务锁必须承担跨进程原子性。
5. correct 同事务使旧关系 superseded、保存旧目标 exclusion、写新关系和确认依据、递增关系修订/查询代数。任何一步失败全部回滚。disable 同事务停用并写 exclusion；invalidate 则待复核。候选 new 属性没有已存在目标 ID 时不能先建共享空字段再记关系。
6. 回读目标关系、排除、回执和修订后才返回 saved，返回 profile_write=none。断线重试先查同 key；不能因超时再换 key 重建。关系更新与资料答案回库分别报告；前者成功不代表后者发生。

错误码：contract_invalid、stale_context、revision_conflict、idempotency_conflict、relation_conflict、excluded_target、scope_mismatch、field_invalid、confirmation_required、restore_requires_explicit_review。服务失败不清空本次草稿或改写其他岗位。

## 字段与历史生命周期

- 仅改显示名：稳定 ID 不变；目录 revision 更新后重新查询核验，刷新关系依赖修订；不得新建字段或重新定位到同名项。
- 等价合并：先证明同对象、同类型/单位/尺度且值无冲突，再由同一字段服务维护旧 ID→新 ID 的可追溯重定向；事务更新受影响关系和排除目标。不能仅改正向关系而漏掉 exclusions，让旧错目标换 ID 复活。值冲突不合并，不自动选较新值。重定向有环或多义即失败。
- 删除/归档、改业务含义/类型：受影响关系 needs_review，不能改绑到近似名称；旧 ID、审计及历史快照可追溯，重新建同名字段不继承旧授权。恢复字段不自动恢复停用关系。
- 关系修订：只失效依赖该关系的未执行预览项及其依赖项，保留选择、草稿与其他已确定项；执行前重新检查目标、扫描、字段、对象/版本与关系修订，避免查询后被纠正仍执行。已执行历史使用当时展开值及原件引用，不按当前默认值重算。
- 限字/语言/公司适用性变化：重新检查答案，不把字段匹配变“新字段”。仅限字改变无需废掉同义身份，仍须当前预览核验新版本/转换结果。

关系服务只改关系命名空间、排除、审计、幂等回执及受影响预览有效性；不得写 facts、versions、files、历史 application_snapshots。离线检查验证这条差异边界，但真实事务、持久重启与并发隔离要在后续产品接入验收。

## P32已确认的事务交接

默认仅本次，包含新属性时也不在共享目录留下空定义。明确回库的差异含目标对象/字段/版本、旧值、新值、共享影响及当前修订；未选内容不变，空输入不是清空指令。稳定资料可更新当前值，任职/项目表达可更新所选版或明确另存。新定义、答案及获准对应关系同事务提交，失败全部回滚，重试同幂等键不重复新增。关系确认本身仍不得改变个人答案。官网手填内容只在用户显式读取后形成差异，不后台回写。
