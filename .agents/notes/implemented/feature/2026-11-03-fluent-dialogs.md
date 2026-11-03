# Agent Note: 对话框统一为 Fluent 风格

Status: implemented

## Problem

主界面换成 QFluentWidgets 后，导出完成/错误/正则/批量排除四个对话框仍是原生 `QDialog` 外观（白底直角、系统标题栏、默认按钮），与主界面割裂。用户反馈「页面与主页面显示风格不一致」。

## Decision

四个对话框全部改为 QFluentWidgets 的 `MessageBoxBase` 派生类：

- 新增 `FluentDialog(MessageBoxBase)` 基类：标题用 `StrongBodyLabel`、内容加到 `viewLayout`、主/次按钮固定 140px 宽并两侧留白居中（否则单按钮会被拉满整行）。
- 导出报告：状态摘要 + 每库明细表（数据库/文件/表数/行数/错误），文件列 `Stretch` 自适应避免长路径撑爆宽度；「打开输出目录」次级按钮放在表格下方，「关闭」为主按钮。
- 错误：摘要 + 建议 + 可复制详情，只保留「确定」。
- 正则/批量排除：说明 + 编辑框 + 校验提示 + 「应用到所有已勾选的库」复选框 + 确定/取消；校验不通过禁用确定。
- 测试中构造对话框需传父控件（`MessageBoxBase` 依赖父窗口尺寸计算遮罩与居中），测试新增 `_dialog_host()` 并持有引用。
- 新增 `docs/design/capture_dialogs.py` 生成四类对话框截图 `docs/design/ui-dialogs.png`，便于视觉回归。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `295e9de`

## Alternatives considered

**保留 QDialog，只套一层 QSS。** 改动小。不选：遮罩、圆角、阴影、标题栏都要自己仿，容易再次出现「原生残影」类问题；且与主界面控件风格仍难统一。

**简单场景用 `MessageDialog`，复杂场景继续 QDialog。** 省代码。不选：只有错误提示适合 `MessageDialog`，导出报告与正则编辑都需要自定义内容；混用两种风格反而更割裂。

**自写无边框 QDialog + 遮罩 + 阴影。** 完全可控。不选：相当于重写 `MaskDialogBase`/`MessageBoxBase`，没有收益。

## Consequences

**收益：** 四个对话框与主界面视觉统一（圆角、遮罩、Fluent 主/次按钮、字体）；报告表格自适应列宽；截图脚本可回归视觉。

**代价：** 对话框依赖父控件（测试构造需传 host）；`MessageBoxBase` 的按钮布局需要手动固定宽度并居中，隐藏次按钮后要额外留白；测试从原生 QDialog 断言改为 Fluent 组件构造，105 项仍全绿。
