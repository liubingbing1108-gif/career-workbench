# 跨对话接续与自动记账

这是开发Agent的职责，不要求使用者每次提醒。所有新任务、恢复的旧任务、切换到此项目的任务，都先读AGENTS.md及其入口，执行 `python scripts/project_handoff.py status`，再读ROADMAP、HANDOFF_CONTEXT和[自动接续索引](PROJECT_ACTIVITY.md)。当前任务恢复时回读最新规范及影响文件，不依赖旧对话缓存。

## 开工

确定任务标识和确切文件范围，执行：

```sh
python scripts/project_handoff.py begin --task example-fix --scope scripts/example.py docs/EXAMPLE.md
```

例子路径须换成实际文件或目录；未创建文件可提前登记。登记记录工程文件哈希和范围，存于忽略且不分发的`.project-local`，不读取运行资料、凭据或简历。相同/上下级范围被其他活动任务占用时拒绝登记；先协调到不重叠范围或等其交接，不强行解除。独立Git工作树仍须在合并时核对冲突，文件登记不能跨机器锁定工作树。

中断后保留任务，继续原task，不删除登记假装工作完成。计划范围扩大时，先收尾现有任务，再用新task登记新增范围；不先越界写入再补登记。只读讨论无需开工登记；讨论造成规范/状态修改就属于需记录的改动。

## 每次交付或中断前

Agent填写一份临时JSON；不得放真实用户资料、聊天内容、凭据或个人路径：

```json
{
  "kind": "fix",
  "summary": "Describe the concrete change",
  "capabilities": ["distribution"],
  "validation": "Actual commands and results; clearly state checks not run",
  "compatibility": "API/storage/permissions impact or unchanged",
  "handoff": {
    "task": "example-fix",
    "status": "in_progress",
    "next": "Finish the listed acceptance checks",
    "docs": [],
    "docs_reason": "Explain which authoritative specifications changed, or why no change was needed"
  }
}
```

`kind`沿用GOVERNANCE；`status`为planned/in_progress/blocked/complete。`docs`列已修改的公开规范路径，`docs_reason`须解释影响；私有任务的规范路径留在本机回执，公开摘要只写通用影响。测试完成前不要写complete，也不要把代码交付说成已部署。

```sh
python scripts/project_handoff.py record --task example-fix --input /tmp/handoff-input.json
python scripts/check_project.py
python scripts/check_docs.py
python scripts/project_handoff.py status
```

程序对比已登记范围，自动计算新增/修改/删除文件，生成唯一且不覆盖旧文件的`.changes`片段，并同步PROJECT_ACTIVITY。临时JSON不需要提交。私人源目录使用同一发布白名单映射公开路径；私有文档路径仅记本机回执，不混入公开片段。普通公开clone直接使用仓库相对路径。变更片段是唯一更新账本，自动索引是其视图；ROADMAP/HANDOFF均链接此视图，不再手抄多份最新状态。

in_progress/blocked保留占用，complete释放。后续仅补测试结果或状态时，也可再次record生成状态记录，不需要伪造源码改动。closed任务不能再次写入，后续变更新建task。没有已完成实现的planned/blocked不能通过改状态冒充完成；检查器验证格式和同步关系，事实由Agent证据与审阅负责。

## 检查与恢复

- `check_project.py`拒绝新片段缺接续信息、错误规范路径引用和过期自动索引；现有run_tests入口首先调用此检查，CI沿用同一检查。
- PR完整基线检查仍要求所有实际变动路径被新片段覆盖；生成的PROJECT_ACTIVITY和SOURCE_MANIFEST无需手列。索引合并冲突时从片段重新执行`sync`，不人工选择一侧覆盖另一侧。
- 私人源码导出首先检查项目契约、索引及活动登记；有未记账的范围内改动时拒绝导出。记录为in_progress后允许生成候选包做隔离验收，候选包不等于允许发布；正式发布仍须完成有关任务的验收与审阅。产品启动、导入、填写、存储和运行Agent均不调用这些管理工具。
- record/sync使用短时写锁并原子替换文件；进程中断后不得盲删锁。确认无写入者，再核对片段、本机回执和源码；已落盘片段不重写，补新的纠正/状态记录，运行sync恢复索引。出现错误不得报告已记账成功。
- 改动已有产品行为仍需更新对应权威需求/接口和验收；自动记账不替代这些内容。纯工程变化说明规范无影响即可，不新增虚假的产品决定。

## 自动化的实际边界

规则由支持AGENTS.md并在此工作区运行的宿主读取；普通文件不能向所有已打开对话强制注入新系统指令，也不能控制不读取规则的第三方Agent。这里用统一入口、任务登记、现有测试/导出检查及PR检查减少遗漏，不声称绝对自动服从。

本机检查不会持续监听任意文件编辑，也不会把未登记的编辑自动判定为某人的任务。公开仓库仍需维护者启用必需CI和PR合并保护，才能在远端阻止绕过检查的合并。不要为了管理新增产品后台进程、修改用户全局Agent配置或自动发送其他聊天消息。

## 分工交付的接收检查

当用户指定某个任务只交付独立产物、由另一任务维护共享PRD/索引时，遵循该分工，不抢写共享文件。接收方除了更新PRD与交接摘要，还应核对交付任务是否有独立片段和task状态；没有则在核验产物与证据后追加标明“事后补登记”的状态记录。不得伪造原任务的开工基线、文件差异或未执行的测试。产品未接入、未部署或未纳入公开导出的状态分别保留。

`status`里没有活动登记，只表示已登记任务的状态；不表示其他聊天没有工作。已关闭任务不会持续比较后来的文件变化；`check_project`的静态成功不证明所有工作区编辑均被覆盖。复核遗漏时应结合实际任务、独立交付报告、最新文件与完整PR基线，不能只看绿色检查。
