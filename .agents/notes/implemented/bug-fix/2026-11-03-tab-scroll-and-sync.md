# Agent Note: 修复 Tab 滚轮滚动与左侧点击不同步

Status: implemented

## Problem

IDEA 风格 Tab 上线后用户反馈两个问题：

1. Tab 多了无法用鼠标滚轮横向滚动，后面的库看不到。
2. 点左侧数据库，右侧表清单数据变了，但 Tab 高亮没有跟着切换。

## Root cause

- QFluentWidgets 的 `TabBar` 继承自 `SingleDirectionScrollArea`（QScrollArea 的子类），滚轮事件交给内部 viewport/smooth scroll 处理，垂直滚轮不会驱动横向滚动条；`setScrollable(True)` 只设置 Tab 最小宽度，与滚轮无关。
- `_activate_database()` 只更新 `_current_db` 与表清单，没有同步 `database_tabs.currentIndex`；只有 Tab 点击和 `_rebuild_database_tabs()` 会设置索引。

## Decision

- 新增 `ScrollableTabBar(TabBar)`：在 viewport 安装事件过滤器，`QEvent.Wheel` 时把 `angleDelta` 映射到 `horizontalScrollBar().setValue(value - delta)`，接受事件避免冒泡；仅当能滚动（maximum > 0）时拦截。
- `_activate_database()` 开头调用 `_sync_tab_current(db)`：按 `_checked_databases()` 顺序求索引、屏蔽信号 `setCurrentIndex`，并 `_ensure_tab_visible(index)` 把标签滚进可视区。
- `_rebuild_database_tabs()` 重建后也确保当前 Tab 可见。
- 回归测试：`ScrollableTabBar` 滚轮事件改变滚动条值；左侧点击后 `_current_db`、Tab 索引、Tab 文本三者一致（共 115 项）。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `6745991`（Tab 功能）、本次修复提交

## Alternatives considered

**用 `setScrollable(True)` + 依赖组件库自带滚动。** 最省事。不选：实测 viewport 接受事件但不改变横向滚动条，滚轮无效。

**给 TabBar 加左右箭头按钮。** 更接近 IDEA。不选（当前）：需要自绘/布局箭头并处理边界，成本高；滚轮滚动已满足需求，后续可再加箭头。

**左侧点击只重载表清单，不联动 Tab。** 维持现状。不选：用户明确要求切换 Tab；且左侧点击与 Tab 状态不一致会造成困惑。

**在 `_on_database_highlighted` 里单独设置 Tab 索引。** 只修一个入口。不选：Tab 点击、关闭、重建、程序激活等多入口都需要同步，集中到 `_activate_database` 更可靠。

## Consequences

**收益：** 库多时可用滚轮横向浏览所有 Tab；左侧点库与 Tab 高亮始终一致，当前 Tab 会自动滚入可视区。

**代价：** `ScrollableTabBar` 拦截滚轮后，若用户想用滚轮滚动外层页面则无效（本界面 Tab 区本来也无需外层滚动）；`_sync_tab_current` 在每次激活时多做一次索引查找与可见性计算（库数量很小，开销可忽略）。
