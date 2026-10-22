# 数据与接口

`.runtime/profile/lab.sqlite` 保存资料状态 JSON 与原附件 BLOB；`.runtime/management/management.sqlite3` 保存岗位、日期、执行关联、请求回执及迁移账本。`.runtime/locations.json` 定位两库，初装采用仓库相对路径。实际数据库不分发。

资料字段定义、经历记录、内容版本与默认引用分开。教育组合引用同一记录，不能复制成多套事实。本次会话绑定管理岗位 ID，保存网站要求、映射、选择、临时覆盖、附件和执行历史；仅本次不回流共享资料。同链接的两个岗位不能共用确认授权。

管理 revision 防过期覆盖，receipts 只防单次请求重放，不阻止用户独立录入重复岗位。人工招聘日期与操作日志分开。岗位删除在两库事务中删除关联会话，保留共享资料与 BLOB；回滚日志模式已测试，其他事务模式不得直接假定可用。

| 接口组 | 入口示例 |
|---|---|
| 健康 | GET /api/health |
| 资料 | GET /api/state、/api/profile-groups、/api/increments |
| 维护 | POST /api/fields、/api/entries、/api/profile、/api/versions/create |
| 导入 | POST /api/import、/api/import/resolve |
| 材料 | GET /api/application、/api/preparation、/api/preparation/bundle |
| 决策 | POST /api/website/choices、/api/website/version、/api/website/answer |
| 准备 | POST /api/preparation/open、/api/preparation/preview、/api/preparation/start、/api/preparation/pause |
| 浏览器 | POST /api/browser-launch，prepare 连接、focus 接手 |
| 管理 | /management/api/bootstrap、/jobs、/preview/text、/import |
| 官网查找 | /management/api/jobs/:id/resolution 及 /resolution-choice |
| 扩展 | /api/executor/*，会话令牌与 URL 检查，不作为公网 API |

具体方法和请求字段以两个 `server.py`、`preparation.py`、`executor_bridge.py` 为准，测试包含虚构请求。管理写接口须携带本机 bootstrap 的 X-Management-Token，写请求校验 origin；不要把令牌发给远端 Agent。资料／扫描输出含私人内容，不写公共日志。

[执行器 API](../prototypes/icbc-native-extension/API.md) 与 [类型](../prototypes/icbc-native-extension/protocol.d.ts) 定义 scan、readOptions、readDateFormat、ensureRecords、validate、execute、status、verify、uploadAttachment、saveDraft、cancel。没有任意脚本或最终提交方法。

受理不等于完成，complete 只代表当前计划。材料回报单列 filled、verified、save_acknowledged、persistence_verified、persisted、expected_count、attachment_verified。只有重开后的预期材料及所选附件均匹配，材料层 saved 才为真。


直接申请页优先核对指定页面的公共公司、租户与具体岗位；资讯/首页先选具体岗位。用户明确指定的HTTPS表单按要求解析，身份/标题差异提示，原来源、人工状态和日期保留。已登录动态页无静态正文不等同需重新登录，也不直接启动漫长全网查找。执行始终绑定本人指定或已核验的本岗位目标。

插件独立只读复核模式不填写、上传、新增记录或暂存。异步搜索页壳不视为表单已加载。实际无草稿且重开丢失时，恢复已确认材料后保留当前页并提示本人提交，不称保存成功。当前包1.3.9/核心1.2.36/客户端1.2.13，协议v1，权限不变。有限真实平台验证不能代表任意网站、隐藏表单或跨系统均已验收。

官网本人接手（mode=focus）只定位已有标签页，不重新读取表单、匹配、轮询材料或启动填写；该边界已加入虚构回归。

## 简历导入确认契约（D99）

新导入携带`parser_contract=resume-material-parser/v1`和`review_contract=resume-review/v1`，由识别器显式加载Skill并记录`skill_sha256`。`document_blocks`保留清洁`text`、转换`raw_text`和来源定位；原件仍通过`file_id`引用。有布局疑点时追加原PDF/Word结构及可用页面的证据，`source_review`说明核对结果与限制。旧已确认导入不自动迁移或重新识别。

`POST /api/import/review`接收`import_id`、当前`revision`及`answers`列表。每项包括问题`id`、`action`（skip/original/apply/note/confirm）、可选`values`字段映射及`note`。`confirm`仅用于明确核对原件后的归属确认；`apply`只允许问题列出的字段，非空更正记录为用户确认来源。未提供的问题默认跳过；已保存对象的问题保持原决定且不可改写。返回completed、updated_fields、skipped；重复相同提交返回replayed。过期修订/已保存对象改写返回409，不发生部分写入。

提交只更新导入候选及`review_answers`，不写共享资料。`review_completed`仅表示表单已处理，不表示所有疑点均已解决：缺失日期可留空；原件归属疑点跳过或仅备注后，该对象仍不能保存，其他确定对象可先保存。可重新打开未保存对象的问题补充确认，已保存对象锁定；原文引用失败不能靠归属确认解除。

之后沿用`/api/import/identity`确认同一对象，`/api/import/resolve`按完整资料组处理：replace保留本次表述、new保留同一对象的完整替代表述、ignore只忽略本次。事实冲突另需明确确认。缺值不清空旧值；每组的确认、修订及事务保护继续有效。历史D85字段级版本描述已由D87及D99整组版本接续，不把多次获奖或不同经历当作同一对象的版本。
