# Agent Note: 表清单显示表注释

Status: implemented

## Problem

表清单只有名称、类型、估算行数，看不出表是干什么的；库大时只能靠表名猜，挑选要排除的表很费劲。用户要求列表加上表注释。

## Decision

- `TableInfo` 增加可选字段 `comment: str = ""`（保持既有位置参数兼容）。
- `MySQLDialect.list_tables` 的尽力统计查询扩展为 `SELECT TABLE_NAME, TABLE_ROWS, TABLE_COMMENT`，仍走 1.5 秒 `max_execution_time` 超时兜底；超时/失败时行数与注释都为空，不阻塞列表。视图的 `TABLE_COMMENT='VIEW'` 视为空字符串。
- 表清单新增「注释」列，显示在估算行数之后、说明之前；列宽 `Stretch`、超长截断并通过 tooltip 显示全文。
- 注释列可点击排序（与名称/类型/行数/说明统一逻辑）；表格关闭 `setWordWrap`，说明列改为固定宽度 + tooltip，避免长原因文本换行撑高行。
- 测试：方言注释解析（含视图注释过滤）、表清单注释显示与排序；共 108 项。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `bcef7c2`

## Alternatives considered

**只在「说明」列显示注释（未排除时显示注释，排除后显示原因）。** 少一列、界面宽裕。不选：两列语义不同，合并后用户看不出表被排除的原因与表本身注释；注释是常驻信息，应该一直可见。

**注释只放 tooltip（悬停名称显示）。** 不占列宽。不选：用户明确要「列表上看到」，tooltip 不可浏览、不可排序。

**单独查询 `information_schema.TABLES` 取注释，不设超时。** 能拿到全部注释。不选：之前已经踩过该查询冷缓存卡 5–15 秒的坑，列表必须秒开；注释只是辅助信息，可接受冷缓存时暂缺。

**用 `SHOW TABLE STATUS` 一次取行数+注释。** 语义更直接。不选：它同样依赖统计信息且无法设置 `max_execution_time`（超时不受控），风险不比当前方案低。

## Consequences

**收益：** 表清单能直接看到中文表注释，挑表/排除表不用猜表名；注释列可排序；超长注释不破坏行高，tooltip 可看全文。

**代价：** 冷缓存库的注释可能为空（与估算行数同一超时兜底）；多一列后名称/注释宽度变窄，长表名和长注释会被截断（tooltip 兜底）；`TableInfo` 的相等性包含 comment，序列化/测试构造需注意（默认空串已兼容）。
