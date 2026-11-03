# Agent Note: 日志改独立窗口，消除主页面变形

Status: implemented

## Problem

用户反复点击「日志」后主页面变形：左侧库列表被压扁、右侧表区域几乎消失、底部导出栏和内容溢出/裁切。

根因是日志面板内联在主窗口底部栏里：`log_container` 展开会让底部 `ElevatedCardWidget` 瞬间长高，而窗口高度固定、主区域（QSplitter）没有最小高度保护，`QVBoxLayout` 只能把主区域压到接近 0；另外导出结束后 `progress_container` 一直可见，进一步抬高底部栏。窗口小时总最小高度超过可用高度，内容被裁切，看起来就像「页面变形」。

## Decision

- 运行日志改为**独立 Fluent 窗口** `LogDialog(FluentDialog)`：只读文本 + 复制/清空 + 关闭；导出进行中打开会实时追加（`_log` 里检测窗口可见时 `append_line`），完全不再影响主窗口布局。
- 底部栏移除 `log_container`，`log_button` 改为普通按钮（打开窗口），不再 checkable。
- `progress_container` 只在导出期间显示，导出结束/失败后隐藏。
- 顺带把最后几处原生 `QMessageBox` 全部换成 Fluent 对话框：
  - `InfoDialog`：关于
  - `ConfirmDialog`：删除配置、覆盖已有文件、导出中退出
  - `TextViewDialog`：导出预览（只读、可复制）
  - `ErrorDialog`：`_show_error` 与工作线程错误
- 测试同步调整：日志按钮断言改为 `isCheckable() is False`，新增 LogDialog/ConfirmDialog/TextViewDialog 用例，共 107 项。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `3978a21`

## Alternatives considered

**展开日志时自动把窗口调高，收起时恢复。** 实现简单。不选：屏幕高度有限（1080p 下窗口 860+日志 180 就可能超屏），且用户可能已经最大化/调整过窗口，自动改尺寸很突兀。

**给日志面板加固定高度 + 主区域设最小高度，溢出时整体滚动。** 布局上更保守。不选：主界面是桌面工具不是网页，出现整页滚动条很别扭；日志本身应该可独立查看/复制。

**日志做成主窗口内的浮层抽屉（overlay），不占布局。** 能保持页面不动。不选：需要手写定位、阴影、拖拽、层级与焦点处理，复杂度明显高于独立窗口，收益不大。

**保持内联但重排底部栏（日志做成 Tab 与设置切换）。** 减少同时展开的内容。不选：日志可读高度仍然很局促，且仍会挤压主区域。

## Consequences

**收益：** 主页面尺寸与布局完全不受日志影响；导出结束底部栏恢复干净；日志可以边导出边查看、复制、清空；全应用再无原生 QMessageBox 风格弹窗。

**代价：** 日志窗口是模态 `MessageBoxBase`，打开期间主界面被遮罩，需关闭后继续操作（导出后台线程不受影响）；日志内容每次打开从缓冲重建（打开时的快照 + 打开期间实时追加）；底部栏不再有「展开日志」的状态，测试相应调整。
