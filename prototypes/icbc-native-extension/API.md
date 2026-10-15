# 填写执行器接口 v1

当前注入核心版本 `1.2.36`，后台客户端 `1.2.13`，包版本 `1.3.9`，协议 `schemaVersion: 1`。安装见 [README](README.md)，结构类型见 [protocol.d.ts](protocol.d.ts)。

## 职责和入口

资料库保存资料 → 上层模型理解网页要求并返回资料位置 → 上层程序核对位置、取出已确定的答案 → 执行器操作控件并回读。

执行器只接收“字段标识＋值”，不读取全部简历，不选择教育集合、经历、版本或联系人，不调用模型。`sourceRef` 是可选的来源标识，只透传到结果，当前不负责验证它指向哪份资料。模型输出应经过上层程序核验，不能让模型提交任意脚本、选择器或网页操作。

Chrome 扩展的页面载入 `client.js` 后：

```js
const client = new JobFillClient(tabId); // 用户明确选中的目标标签页
const response = await client.call('scan', {});
if (!response.ok) throw new Error(response.error.message);
const snapshot = response.result;
```

客户端检查用户主动调用的 HTTPS 标签页；扫描绑定该页的精确 URL，页面切换使旧扫描失效，再用 `chrome.scripting` 在隔离环境运行代码。网页本身不能通过同名全局变量调用执行器。没有网页 postMessage、external messaging 或 native-messaging。D69新增本机8768顶层内容监听转交短效启动票据，D79后台直接建立单一控制器，不再打开控制页，claim后仅向本机127.0.0.1:8768发送请求并打开该岗位HTTPS目标。原始招聘网页不能发起任意执行命令。manifest1.3.9沿用D69增加的可选HTTPS权限，仅在首次明确授权手势申请；首次启用后沿用同一HTTPS范围。

## 方法

| 方法 | 输入 | 结果与作用 |
|---|---|---|
| `scan` | `{}` | 当前可访问字段、分区、能力、扫描编号；只读 |
| `readDateFormat` | `{snapshotId,fieldId}` | 打开日期弹层只读其年月/年月日精度并关闭；不改值 |
| `readOptions` | `{snapshotId,fieldId}` | 读取原生或展开自定义菜单的候选，再关闭菜单；不选答案 |
| `validate` | 填写计划 | 全部计划预检查；零写入，不代表已选到动态下拉选项 |
| `ensureRecords` | 分区目标条数 | 补足缺少的记录，完成后返回新扫描 |
| `execute` | 填写计划 | 返回受理编号；在页面异步填写及回读 |
| `status` | `{requestId?}` | 指定请求或最近任务的状态、逐项结果、耗时和错误 |
| `verify` | `{requestId}` | 再读已完成任务的页面值；不写，不验证服务器保存 |
| `cancel` | `{}` | 停止后续动作；已发生的输入不回滚 |
| `openSection` | `{sectionId}` | 工行九个普通分区间切换并返回新扫描 |
| `saveDraft` | 版本、请求编号、扫描编号 | 已接通草稿按钮的独立保存任务；检查明确成功反馈，不提交 |
| `uploadAttachment` | AttachmentPlan，见类型契约 | 当前扫描的唯一上传入口＋所选原件；已有同名附件保留，完成后回读文件名 |

方法失败返回 `{ok:false,error:{code,message,details?}}`。方法受理成功返回 `ok:true` 并不代表填写完成。写入任务需要轮询 `status`，只有 `status:'complete'` 才完成；`failed`、`cancelled` 可能已有部分输入，需查看 `results` 和 `error`。

`complete` 只表示该指令覆盖的字段完成，不等于整张申请完备。`saved` 和 `submitted` 单独表示；普通填写不会主动点击保存，但网站可能自行保存或缓存；`saved:false` 仅表示执行器没有调用保存。全部现有方法都不会提交申请。

## 字段扫描

字段包含 `fieldId / label / kind / sectionId / recordId / required / disabled / description / constraints / options / currentValue`。另含 `context`（分区、控件驱动、占位说明等）和 `blockedReason`。日期精度通过 `kind` 区分年月日、年月和年；多选使用字符串数组，复选框使用布尔值。未支持控件以 `kind:unsupported`／disabled 及原因返回。`maxLength` 仅在网页提供时返回。

`coverage` 固定为 `currently-accessible-fields`：未展开、后续页面、条件字段、附件及不在适配范围的字段不算已扫描。多个记录中相同标签必须通过 `fieldId`、`recordId` 和所属分区区分，不能只按“学校”或“描述”匹配。

原生选项返回 `enumerated`；自定义下拉初始返回 `options.state:'requires-opening'`，不会假装已经穷举选项；写入时打开真实菜单并精确匹配。`readOptions` 可在当前扫描上读取候选，支持 generic-dom；虚拟列表或动态搜索只返回本次可见项 `visible-options`、`complete:false`，不保证全集。旧飞书/工行驱动未实现此方法会返回 UNSUPPORTED。当前适配器缺少的信息不能由上层当作没有限制。

## 填写计划

下面是结构示例，扫描编号和字段标识必须来自当前 `scan`，不可照抄到另一个页面：

```json
{
  "schemaVersion": 1,
  "requestId": "application-123-fill-1",
  "snapshotId": "由当前扫描返回",
  "assignments": [
    {"fieldId": "由扫描返回的专业字段", "value": "资料库中已经选好的专业", "sourceRef": "profile/education/record-2/major"}
  ]
}
```

- 默认 `overwrite:'emptyOnly'`：已有不同值拒绝覆盖；已有相同值只回读，结果为 `unchanged`。
- 上层已决定改写时可指定 `overwrite:'ifUnchanged'`；仍要求当前值与扫描时完全相同，用户扫描后手动修改会返回 `VALUE_CHANGED`。
- 重复字段、未知字段、超字数、无效日期、不支持的属性或控件在首次写入前拒绝。不给文本静默截断，不替用户猜选项。
- 页面切换、新扫描、节点被重建或经历索引变化后，旧扫描不可继续执行。完成填写后若需第二份计划或保存，应先重新扫描。
- `assignments` 为 1–500 项；多选为不重复的非空字符串数组。日期分别为 `YYYY-MM-DD`、`YYYY-MM`、`YYYY`。
- 可选字段可用空字符串显式恢复为空，已有值仍需 ifUnchanged；驱动不支持清空会在预检查拒绝。Ant 日期/下拉使用控件自带清除按钮；必填不能清空，空多选数组仍不支持。不提供删除经历接口。

## 新增多条经历

已支持新增的分区统一使用“达到几条”，不使用“再加几条”：

```js
const req = {
  schemaVersion: 1, requestId: crypto.randomUUID(), snapshotId: snapshot.snapshotId,
  sections: [{sectionId: 'education', count: 3}]
};
const accepted = await client.call('ensureRecords', req);
// 轮询这个 requestId；完成后用 job.snapshot 的字段标识和 snapshotId 组成填写计划。
```

当前两条、目标三条，仅加一条；已经三条就不加；超过目标不会删除。每个分区目标 0–20 条，网站实际不允许新增时停止并报错。行数由上层根据网站要求和资料集合决定，不能由执行器默认取一条或一律全部添加。

同一页面、同一请求编号、完全相同参数的重发返回 `replayed:true`，不再次执行；同编号换参数拒绝。新增后返回新扫描，填写新行用这个扫描。失败时不要盲目换编号重试新增，先重新扫描实际条数，再发送目标条数。

## 最小调用流程

```js
async function unwrap(promise) {
  const r = await promise;
  if (!r.ok) throw new Error(r.error.code + ': ' + r.error.message);
  return r.result;
}
async function waitForJob(client, requestId) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    const job = await unwrap(client.call('status', {requestId}));
    if (!job) throw new Error('当前页面不存在该任务，请重新扫描');
    if (job.status !== 'running') return job;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  await client.call('cancel', {});
  throw new Error('超时，已请求停止；回读实际结果后再恢复');
}
const scan = await unwrap(client.call('scan', {}));
// 上层根据 scan 和用户资料生成 assignments；不在此文件调用模型。
const plan = {schemaVersion:1, requestId:crypto.randomUUID(), snapshotId:scan.snapshotId, assignments};
await unwrap(client.call('validate', plan));
await unwrap(client.call('execute', plan));
const job = await waitForJob(client, plan.requestId);
if (job.status !== 'complete') throw new Error(JSON.stringify(job.error));
const readback = await unwrap(client.call('verify', {requestId:plan.requestId}));
```

这段代码应运行于扩展侧控制器，`client` 和 `assignments` 由调用方提供。弹窗也可直接粘贴 `{method,payload}` 请求；查看结果按钮获取最近任务。弹窗关闭不会中断页面任务，页面刷新则会丢失任务及去重缓存。跨刷新恢复需要上层重新扫描，不能声称已具备持久任务恢复。

工行调用前须本人打开“实习生简历”的一个普通分区。其余分区用 `openSection` 返回新扫描，填好后重新 `scan`，再显式 `saveDraft`。不得把校招简历或声明页当测试页。

## 检查、错误和接续

常见错误：`STALE_SNAPSHOT` / `STALE_FIELD`（重扫）、`VALUE_CHANGED` / `EXISTING_VALUE`（保护已有内容）、`BUSY`（已有任务）、`REQUEST_ID_REUSED`（重复编号换参数）、`READBACK_MISMATCH` / `UNPLANNED_CHANGE`（输入或未计划值发生偏差）、`WEBSITE_VALIDATION`（可见官网错误）、`CANCELLED`、`UNSUPPORTED_METHOD`。底层无法完成选项／日期操作时返回 `ACTION_FAILED` 及具体信息。

同一页面只执行一个任务。每次输入后回读，整组结束等待错误提示稳定，再核对目标值和未计划值；不能保证网站在检查窗口后永远不变化。需要长期稳健性时，继续增加真实页面回归和平台适配。

请求与结果只在页面内存中保留，可能包含个人资料。示例和测试仅用虚构数据；正式控制器不要把完整真实扫描／答案写进普通日志。源码不读 cookie、不访问后台私有 API；附件只传上层已确认的原件，没有最终提交接口。

## 扩展新网站

新增站点适配器实现 `guard/page/fields/sections/write/errors/settle`，可选 `addRecord/openSection/saveDraft/show`，通过当前核心运行。字段内部对象包含真实 DOM 节点以检查节点是否被替换；外部协议不会返回节点或选择器。D65 后通用驱动按 DOM 组件识别，未知控件显式报告，不依靠公司域名或固定资料答案。保留原专用适配器与守卫。新增组件须经过真实页面验证；不能因 URL 可打开就计作填写成功。网站变动只改对应控件操作，模型或资料版本变化只改上层答案选择。


## D65 通用执行范围与计时

`generic-adapter.js` 是新增通用层：原生控件、Moka/Sugar、Phoenix、Ant；其他组件及条件分支按实际识别结果处理。飞书优先根据 ATSX 重复表单结构选择旧驱动，工行实习生范围不变。开放 Shadow DOM 可遍历；`coverageDetails.frameContentsScanned:false` 表示没有扫描 iframe 内容。扫描不等于网站全部问题都已识别。

`scanElapsedMs` 单列扫描；任务的 `preflightMs` 为整份计划预检查，`elapsedMs` 为写入及组末检查，`totalMs` 为后两者相加。不能将工具等待、模型、登录、独立 verify 或正式保存计入这些局部数字。覆盖边界见 [测试](../../docs/TESTING.md)。

读候选示例：

```js
const choices = await client.call('readOptions', {
  snapshotId: snapshot.snapshotId, fieldId: selectedField.fieldId
});
```

读候选会占用页面执行锁，不能同时执行另一份计划。窗口菜单关闭和字段不变后才返回；失败要回读现场，不盲目重试。日期/地区的跨字段影响必须有明确处理，不忽略 UNPLANNED_CHANGE。

刷新、跳转或原型版本升级会丢失页面任务缓存，先记录必要结果再升级，随后重新 scan。默认报告可能含当前个人资料，仅在已授权控制器内使用，不把完整 scan 写入普通日志。


## 工作台自动连接与材料调度

正式入口为本机工作台“开始投递”，扩展接收短效票据，校验岗位和当前官网后自动连接。扫描传回字段元数据，移除 currentValue，Agent 理解后生成待确认资料。手动连接码仅为开发调试能力，不是用户日常步骤。

material-runner.js 按确认条数新增记录、重新扫描、校验、执行、回读和暂存；单个独立项失败不阻止其余已确认项，保留人工修改，不自动删除多余经历。只有本次总预览已确认才生成执行材料；最终不提交。

## D73 当前原件、文本和保存边界

uploadAttachment严格接收schemaVersion/requestId/snapshotId/attachmentId/fileName/mimeType/base64及可选sourceRef；仅使用当前扫描入口，校验页面、附件节点和文件名变化，重放同请求不重复。base64是选定原件字节，最大50MiB，不解析或修改内容；已有同名原附件仅核对。未识别的上传控件不支持，不能声称已传。

程序级execute与verify仍隔离。固定原生文本辅助通过同扩展、准确目标页/频道及一次随机控件标记校验，只做原生文本编辑或原生setter及输入事件；不暴露任意选择器、点击或脚本。Chrome执行环境与消息接口参见 [scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting) 和 [消息传递](https://developer.chrome.com/docs/extensions/develop/concepts/messaging)。

调度器只verify完整execute，部分失败先保留filled计数。附件/保存后再次核对，值丢失降低verified并列出问题；saved与attachment_verified分别回报。支持范围按实际控件与持久回读结果报告，不以局部测试保证全部官网。

正式用户入口从本机工作台自动启动，不要求每次点工具栏或复制码。最终官网提交仍由本人完成。

## D74 进度与启动复用

status的Job可选currentField={label,index,total,sectionId}、progress（当前控件反馈文字）。材料调度上报phase及实际消息，工作台横向节点据此展示，不估算虚假百分比。launch-next复用控制器连接，mode=focus只激活指定官网，mode=prepare后台扫描；扫描前后仍不导入网站已有答案作为个人资料事实。


## 保存持久性（D79）

底层 `saveDraft.saved` 仅表示观察到官网保存回应。材料运行器另外调用受限客户端 `reloadAndScan(expectedUrl)`，仅重新载入同一已确认官网页并重新扫描；按分区、记录序号、字段标签及组件位置比较。报告区分 `save_acknowledged`、`persistence_verified`、`persisted`、`expected_count`、`attachment_verified`；材料层 `saved` 只有预期值及已选附件重开后均在才为真。没有重新打开能力时不能确认保存。该客户端方法不作为任意网页/上层输入的通用导航API。
