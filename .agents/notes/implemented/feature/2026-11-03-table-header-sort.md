# Agent Note: 表清单表头排序

Status: implemented

## Problem

表与视图清单此前固定「表在前、视图在后、名称升序」，库大时找表只能靠搜索；用户希望像常规表格一样点击表头按名称、类型、估算行数、说明排序，方便浏览与挑选要排除的表。

## Decision

`TableListWidget` 支持点击表头排序，名称/类型/估算行数/说明四列可点击，再次点击切换升/降序，表头显示排序箭头；勾选列不参与排序。

实现上**没有使用 Qt 原生 `setSortingEnabled(True)`**：原生排序会重排 QTableWidgetItem，而行号与 `_tables`（TableInfo 列表）按索引绑定的，勾选状态、正则锁定、选中行、搜索过滤都会错位。改为：

- 组件内维护 `_sort_column/_sort_order`、`_excluded/_locked/_reasons/_filter` 状态；
- 点击表头只更新排序状态并重新排序 `_tables`，再按排序后的顺序重建行（名称、类型、行数、说明、勾选、锁定、原因）；
- 重建前用当前行勾选状态同步 `_excluded`，重建后恢复；过滤 `_filter` 重放；
- 排序状态跨 Tab 切换、重新加载表清单保持（`set_tables` 复用当前排序状态）；
- 排序键：名称按小写字母序、类型按「表在前/视图」、行数按数值、说明按文本；稳定性由名称兜底。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `b57cb4c`

## Alternatives considered

**Qt 原生排序（`setSortingEnabled(True)` + 自定义 `QTableWidgetItem.__lt__`）。** 代码最少、排序箭头与交互由 Qt 提供。不选：排序后行号与 `_tables` 列表不再对应，`excluded_names()`、`selected_names()`、`update_reasons()`、`apply_filter()` 全部要改成按行数据反查名称；且勾选状态在重排/重建时容易丢。手动排序牺牲很少，却保持既有接口不变。

**只在加载时排好序，不提供交互排序。** 无交互成本。不选：用户明确要点击表头排序。

**固定名称排序 + 搜索即可。** 最简单。不选：估算行数/类型排序对挑大表、日志表很有用。

## Consequences

**收益：** 表多时可按名称、类型、行数、说明快速定位；排序状态切换 Tab / 重新加载不丢；勾选、锁定、过滤状态跨排序保持一致。

**代价：** 每次点击表头会重建整张表（几百行以内无感）；新增排序状态与两次同步逻辑（`_sync_excluded`）；`_tables` 顺序由组件自己负责，外部不应假设其顺序；测试新增名称/行数排序与勾选状态保持用例，共 105 项。
