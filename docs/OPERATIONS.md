# 运行与恢复

初始化见 [安装](SETUP.md)。正常启动只读取配置中的两库，缺任一数据库即拒绝启动。不要用初始化代替恢复，也不要并行运行多个工作目录下的生产实例。

本机日志与 PID 在 `.runtime`，仅供本人排障。关闭终端不一定停止后台进程；macOS/Linux `python scripts/start_workbench.py --restart` 核对 PID 对应命令后重启。不要在实际填写中重启。Windows 先结束自己启动的 Python 进程再启动，不随意结束其他 Python 任务。

## 备份

暂停填写并停止服务，完整复制 `.runtime` 到本人控制的私有存储，包含两库、配置和原件。数据库采用 SQLite，不能在写入时只拷贝主文件而遗漏事务日志。可使用 sqlite3 backup API，但两个库的联合备份仍需无写入窗口。

核对备份两库 `PRAGMA integrity_check` 均为 `ok`，比对记录数量及文件 BLOB 哈希；不把哈希清单或文件名公开。确认备份有效后才能迁移或升级存储。

## 恢复

停止服务，保留损坏现场的副本，恢复完整两库和 locations 配置到原位置。相对路径相对项目根目录；跨目录恢复时检查旧绝对路径。启动后核对资料、版本、附件、岗位和历史，不自动重新发送旧填写任务。原网站现场不会被数据库恢复。

无恢复副本时不要创建空库声称“恢复成功”。丢失的个人事实由本人重建。

## 更新

保存备份，更新源码和依赖，在隔离目录跑虚构测试，确认后重启。扩展代码升级需在 Chrome 重新加载并刷新工作台，不能把磁盘版本当作浏览器实际版本。首次 HTTPS 权限启用后，正常申请无需手动开插件。

GitHub 中只有脱敏源码，不承担个人数据备份职责。回退源码前核对数据库结构兼容性；不要把旧数据库覆盖回去而丢失新增资料。

## v0.4.0：明确启用资料契约30

升级源码不会自动切换旧资料库。先按上文停止服务与填写，在本人控制的私有目录完成备份和演练；路径从自己的`.runtime/locations.json`读取，禁止照抄他人的数据路径或用空库替代。新初始化的兼容库也可走同一明确启用流程。

```sh
python scripts/migrate_profile_refactor.py rehearse --source <资料目录>/lab.sqlite --management-source <管理目录>/management.sqlite3 --output <新的私有演练目录>
python scripts/migrate_profile_refactor.py review --output <私有演练目录> --decisions <本人确认的JSON文件>
python scripts/migrate_profile_refactor.py apply --output <私有演练目录>
python scripts/start_workbench.py
```

核对文件包含`confirmed:true`、唯一`request_id`、报告中的`expected_hash`及`commands`。`pending`处理具体待核对ID，`record`明确保存对象字段，`normalize_startup`与服务共用启动升级逻辑；样例结构见迁移脚本测试，不能用样例内容替代真实事实。先确认全部可解决的旧值/类型/考试歧义；缺当时实际材料的历史项只能标记保留，不能填当前答案伪造。演练目录含私人信息，绝不能上传到仓库。

正式切换前，在副本验证启动稳定、重复apply和rollback。apply拒绝来源/原件/管理库变化及仍在执行的任务。启动后回读当前资料、旧草稿、原件和岗位；旧材料预览已失效，需重新预览确认。rollback仅接受切换后尚无新写入的精确候选状态；有新写入先保留，再制定前向修复，不能直接覆盖备份。
