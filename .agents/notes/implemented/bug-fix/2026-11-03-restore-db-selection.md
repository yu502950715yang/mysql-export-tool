# Agent Note: 连接后回显上次勾选的数据库

Status: implemented

## Problem

连接成功后左侧数据库列表全部未勾选，上次保存的库选择没有回显。

## Root cause

`_test_connection()` 与 `_refresh_databases()` 都会先调 `_collect_profile()`。它用当前 `database_list` 的勾选状态覆盖 `profile.selected_databases`。但应用启动、切换配置时 `database_list` 还是空的（`_apply_profile` 清空），于是：

1. 点「连接」→ `_collect_profile()` 把 `selected_databases` 覆盖成 `[]`；
2. `_on_databases_loaded()` 读到的已经是空数组 → 全部未勾选。

## Decision

- 新增 `_database_loaded` 标记：`_apply_profile`/`_on_databases_loaded` 之前为 False，列表真正加载完成后置 True。
- `_collect_profile()` 仅在 `_database_loaded` 为 True 时才用列表状态回写 `selected_databases`；否则保留配置中的已保存值。
- 列表加载完成后按原有逻辑回写（用户改选、保存/刷新不受影响）。
- `_rebuild_database_tabs()` 结束时同步左侧列表当前行到激活 Tab 的库，回显时能看到当前库高亮。
- 回归测试覆盖：连接前 collect 不清空、列表回显勾选、改选后 collect 写入正确（共 111 项）。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `5574d66`

## Alternatives considered

**在 `_test_connection`/`_refresh_databases` 里先保存表单字段、不收集列表状态。** 需要把 `_collect_profile` 拆成「连接字段」与「列表状态」两部分，调用点容易漏。不选：标记位更简单、集中，且语义明确（列表没加载就不该覆盖列表状态）。

**连接前先根据已保存的 selected_databases 预填充列表。** 此时还没有数据库名列表，无法填充；且刷新时仍会被覆盖。不选：治标不治本。

**只在 `_on_databases_loaded` 里从 config 重新读（不回写）。** 不回写会导致用户改选后刷新丢失。不选。

## Consequences

**收益：** 连接/刷新/切换配置后能正确回显上次勾选的库和当前库；用户改选后保存/刷新行为不变。

**代价：** 新增一个 UI 状态标记；`_collect_profile` 的职责多一层判断（列表未加载时不写 selected_databases）；测试增加一个时序回归用例。
