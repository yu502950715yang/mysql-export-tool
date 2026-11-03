# Agent Note: 表清单加载慢的根因与超时兜底

Status: implemented

## Problem

多库 Tab 界面下，右侧某个库长期停在「加载中…」，用户反馈表清单加载很慢。原实现每个库都执行：

```sql
SELECT TABLE_NAME, TABLE_TYPE, TABLE_ROWS
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = ? ORDER BY TABLE_TYPE, TABLE_NAME
```

再把结果渲染到 TableWidget。

## Decision

先用 `SHOW FULL TABLES FROM <db>` 秒出表/视图清单，再把行数估算拆成独立查询并加 1.5 秒超时兜底：

- `MySQLDialect.list_tables()`：`SHOW FULL TABLES` → `TableInfo(name, kind, 0)`；随后调用 `_estimate_rows(db)` 尽力补 `TABLE_ROWS`；按「表在前、视图在后、名称排序」返回。
- `MySQLDialect._estimate_rows()`：查询前 `SET SESSION max_execution_time=1500`，查询 `SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s`；超时/异常返回 `{}`（行数按 0 展示）；`finally` 中重置 `max_execution_time=0`，避免影响同连接后续导出（MariaDB 不支持该变量时静默跳过）。
- `MainWindow`：加载中每 500ms 刷新「加载中…（N.N 秒）」，让等待可见。

诊断证据（对 `config.json` 里的开发库只读测量，32 个 schema）：首次逐库查询时 6 个 schema 耗时 5–15 秒（最大 `demo_slow_1` 15.05s、`demo_slow_2` 13.74s、`demo_slow_3` 10.59s），同一查询复测全部 0.00s——属于 MySQL 8 元数据/统计冷缓存抖动；修复后 116/160 张表的 schema 列表耗时 0.00–0.04s。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `f430fc1`

## Alternatives considered

**只去掉行数估算（不再查 TABLE_ROWS）。** 最快、最简单。不选：预览与导出报告里的「估算行数」有参考价值，尽量保留；当前方案只在慢库上退化为 0。

**UI 层拆成两步加载：先 SHOW 渲染，再后台补行数。** 列表可以完全零等待，行数列稍后刷新。不选（当前）：需要额外的后台 worker、刷新与竞态处理；在查询上加 1.5 秒上限已经做到列表秒开，改动面小得多。

**只加「取消」按钮 / 更长超时。** 能让用户不卡死，但等待仍然存在。不选：没有解决信息展示依赖慢查询的问题。

**把多库预取改成只加载当前 Tab。** 减少请求量，但当前 Tab 自己的查询仍是慢查询，仍会卡「加载中」。不选：不解决问题根因。

## Consequences

**收益：** 表清单基本秒开；慢库最坏只等约 1.5 秒拿估算行数，拿不到也不阻塞列表；导出/预览/排除逻辑不受影响；加载等待有秒数可见。

**代价：** 冷缓存库的「估算行数」可能显示为空/0（只影响展示与预览的估算值）；同一 worker 里多了最多 1.5 秒的估算等待（可用再看是否拆成异步）；`max_execution_time` 在 MariaDB 上会被忽略（但 SHOW 路径仍然快）。
