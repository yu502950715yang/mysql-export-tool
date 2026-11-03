# Agent Note: IDEA 风格可关闭 Tab（取代多库下拉）

Status: implemented

## Problem

用户在库多时想要「像 IDEA 那样的 Tab，并且可以关闭，关闭左侧就不勾选了」。上一版方案（`2026-11-03-many-databases-dropdown.md`）在勾选 >6 个库时把 Tab 换成下拉，不满足 IDEA 式交互，也无法从 Tab 直接关闭库。本方案取代该方案。

## Decision

右侧始终使用 `QFluentWidgets.TabBar`，按 IDEA 交互：

- **横向滚动**：`setScrollable(True)`，Tab 放不下时用滚轮横向滚动，不再切换成下拉。
- **可关闭**：`setCloseButtonDisplayMode(ON_HOVER)`，悬停/当前 Tab 显示关闭按钮；`tabCloseRequested` → `QTimer.singleShot(0, ...)` 延后把左侧对应库置为未勾选（`itemChanged` 驱动重建），避免在 TabBar 信号里清空自身。关闭当前 Tab 后自动激活剩余第一个库。
- **+ 添加**：`setAddButtonVisible(True)`，`tabAddRequested` 弹出未勾选库的 `RoundMenu`，选择后左侧勾选并打开 Tab。
- 左侧勾选/取消与 Tab 数量始终双向同步；`_rebuild_database_tabs`、`_sync_database_current_row`、`_tab_clicked` 沿用。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `6745991`

## Alternatives considered

**保留下拉，仅加关闭能力。** 不满足 IDEA 式 Tab 的诉求。不选：用户明确要 IDEA 风格 Tab。

**Tab 加左右箭头 + 关闭，替代横向滚动。** 交互更接近 IDEA。不选（当前）：QFluentWidgets TabBar 是 QScrollArea 实现，滚轮横向滚动已可用；加箭头需要自绘控件，收益有限，先用组件库能力。

**关闭 Tab 只隐藏、不改变左侧勾选。** 会出现状态不同步。不选：用户明确要求关闭=取消勾选。

**关闭即立即取消勾选并重建，不延后。** 代码更直接。不选：在 TabBar 的 tabCloseRequested 信号内清空 TabBar 有重入/删除 sender 风险，`QTimer.singleShot(0)` 更稳。

## Consequences

**收益：** Tab 数量不设上限，始终 IDEA 式可关闭/可滚动/可添加；关闭 Tab 与左侧勾选严格同步；不再有下拉与 Tab 两套逻辑，`_on_database_combo_changed` 等分支删除。

**代价：** 库多时需要滚轮滚动（组件库无箭头按钮）；+ 菜单每次重建（库很多时菜单较长）；关闭操作延后一个事件循环执行，测试需 `processEvents`；回归测试替换为「8 库仍可滚动」「关闭 Tab 取消勾选」两项（共 113 项）。
