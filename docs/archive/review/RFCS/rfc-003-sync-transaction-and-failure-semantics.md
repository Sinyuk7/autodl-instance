# RFC-003: 明确 bye/sync 事务语义

## 背景

`src/shutdown.py` 在 `execute("sync")` 后无条件打印“同步完成”。`GitRepoStrategy.push()` 在 commit/push 失败时只 logger.error 并 return；`NodesAddon.sync()` 保存快照失败也不向外抛出。用户可能以为数据已备份成功。

## 用户价值

Job-to-be-done：关机前确认“能安全关机”。触达频率取决于每次关机；失败痛感极高，因为实例释放后无法补救。

## 提议

MVP：
- `sync` 返回结构化结果：每个插件 SUCCESS/SKIPPED/WARN/FAILED。
- `bye` 汇总输出并在任一关键插件失败时退出非 0。
- `userdata` push 失败时给出下一步：检查网络、SSH key、手动 `git status && git push`。
- 写入 `sync-report.json` 到数据盘，记录本次 lock/snapshot/git push 状态。

## 非目标

- 不实现复杂 rollback。
- 不阻止用户手动关机。
- 不做后台重试 daemon。

## 替代方案

方案 A：所有错误直接 raise。简单但可能中断后续非关键清理。

方案 B：保持日志，不改流程。风险继续存在。

本方案使用结构化结果，兼顾继续执行和最终失败。

## 影响面

- `src/core/task.py`
- `src/main.py:execute`
- `src/shutdown.py`
- `src/addons/userdata/strategy.py`
- 插件 sync 返回值或上下文收集器
- sync integration tests

不新增依赖。

## 风险

- 改动公共生命周期接口，测试要覆盖 setup/start 不受影响。
- 旧插件 `pass` 需要映射为 SKIPPED。

## 验收标准

- 模拟 Git push 失败时 `bye` 退出非 0，并不打印“可以安全关闭”。
- `sync-report.json` 记录失败插件和建议命令。
- 模拟节点 snapshot 失败但 userdata push 成功时最终状态为 WARN。

## RICE

Reach 3/week, Impact 10, Confidence 0.8, Effort 2.0d => 12.0
