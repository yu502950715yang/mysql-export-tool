# Agent Note: Tab 栏溢出时显示横向滚动条

Status: implemented

## Problem

Tab 多了以后虽然能滚轮横向滚动，但看不到滚动条，用户不知道还能往右滑。QFluentWidgets 的 `TabBar` 固定 `ScrollBarAlwaysOff`、高度固定 46px，自带的横向滚动条不可见，也无法简单打开（会压缩标签区域）。

## Decision

在 Tab 栏下方新增一条独立的横向滚动条，与 TabBar 内部隐藏的横向滚动条双向同步：

- 使用标准 `QScrollBar(Qt.Horizontal)`，高 8px，配一套细圆角 QSS（透明槽、`#C7CBD1` 圆角滑块，hover 变深）；这是全项目唯一的少量手写 QSS，因为 QFluentWidgets 的 `ScrollBar`/`SmoothScrollBar` 必须挂在 `QAbstractScrollArea` 上，不能独立放进布局。
- 同步：`inner.rangeChanged` / `inner.valueChanged` → 更新外部滚动条的 range、pageStep、value 与可见性；外部 `valueChanged` → 写回 inner。`inner.maximum() > 0` 才显示，否则隐藏（不占高度）。
- `_rebuild_database_tabs()` 后用 `QTimer.singleShot(0, self._sync_tab_scrollbar)` 等布局完成再同步一次范围；`rangeChanged` 也会触发。
- `ScrollableTabBar` 的滚轮横向滚动保留，滚轮与滚动条同时更新。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `5a27eea`

## Alternatives considered

**打开 TabBar 自带滚动条（`ScrollBarAsNeeded` + 加高 TabBar）。** 最原生。不选：TabBar 高度固定 46，滚动条会挤压标签；QFluent 样式下原生滚动条也不好看，且组件库内部策略随时可能变。

**使用 QFluentWidgets 的 `ScrollBar`/`SmoothScrollBar`。** 风格统一。不选：这两个类要求父级是 `QAbstractScrollArea` 并接管其 partner bar，无法作为普通布局子控件使用（构造即访问 `parent.horizontalScrollBar()`）。

**用左右箭头按钮代替滚动条。** 更接近 IDEA。不选（当前）：需要自己管理边界、位置与样式，成本高；滚动条加滚轮已够用。

## Consequences

**收益：** Tab 溢出时有可见的细滚动条，可拖动/点击翻页，也能继续滚轮滚动；不溢出时完全隐藏不占空间。

**代价：** 新增一条手写 QSS（项目约定平时避免，但只限这条滚动条）；外部滚动条与内部滚动条需双向同步（已用信号防递归）；布局高度在溢出时增加约 8px，Tab 区可用高度略减；测试新增可见性与双向同步用例（共 116 项）。
