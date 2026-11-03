# Agent Note: 界面层替换为 QFluentWidgets

Status: implemented

## Problem

自绘 QSS 主题（见 `../feature/2026-11-03-simplified-ui-shell.md`）能把布局与配色做干净，但控件细节仍反复出问题：QComboBox 原生下拉按钮残留系统主题色块、QCheckBox 勾选态被画成纯色块、表格与滚动条样式需要逐个子控件覆盖，维护成本高且上限有限。用户明确对组件质感不满意，希望换成开源成熟组件库；同时确认工具**仅在公司内部使用**，GPL 许可可接受。

## Decision

`app/ui` 整体改用 **PySide6-Fluent-Widgets（QFluentWidgets）1.11.3**，删除自绘主题 `app/ui/theme.py`：

- 组件映射：`Card`/状态徽标/空态/表清单/进度/日志全部基于 `CardWidget`、`ElevatedCardWidget`、`CaptionLabel`、`TableWidget`、`ProgressBar`、`PlainTextEdit` 等重写；主窗口使用 `PrimaryPushButton`、`TransparentPushButton`、`LineEdit`、`PasswordLineEdit`、`ComboBox`、`SpinBox`、`CheckBox`、`ListWidget`、`RoundMenu`。
- 结构与交互保持不变：应用栏 + 连接卡片 + 左库右表 + 底部操作栏；导出设置/日志默认折叠；正则命中的表锁定为未勾选、灰显并标注原因；状态徽标/空态/导出快照/线程等待逻辑全部保留。
- 业务分层不变：`app/core`、`app/dialects` 与 `app/cli.py` 零改动，UI 仍是薄壳。
- 页面浅灰背景由根 QWidget 一行样式提供，是唯一保留的内联样式；其余交给组件库主题（`setTheme(Theme.LIGHT)` + `setThemeColor("#2563EB")`）。
- 打包：PyInstaller spec 增加 `PyQt5`/`PyQt6`/`PySide2`/`sip` 排除项，避免构建机同时安装 PyQt5 时触发「multiple Qt bindings」错误。
- 许可：QFluentWidgets 为 GPLv3 / 商业双许可；本工具仅内部使用，README 与 `THIRD_PARTY_LICENSES` 已注明，对外交付前需商业授权或替换 UI 层。
- 测试：97 项全绿；仅将「主题 QSS 生效」断言改为「导出按钮是 QFluentWidgets 的 PrimaryPushButton」。

## Affected repositories

- `mysql-export-data` 分支 `main` commits `75376f5`

## Alternatives considered

**继续自绘 QSS 主题。** 无新增依赖、许可最干净。不选：控件细节需要不断手工覆盖原生子控件，维护成本高且观感上限明显低于成熟组件库。

**QML Material（Qt Quick Controls，LGPL）。** 许可无风险、动画最原生。不选：界面层要用 QML 重写并做信号桥接，等于重建 UI 层；Qt 6.9 的 Material 还没有 Filled/Outlined 按钮类型，主按钮、图标、表格勾选都要手工补，工作量与风险都高于 QFluentWidgets。

**Web 技术栈（pywebview/NiceGUI + Tailwind）。** 观感最现代、前端生态最丰富。不选：要把桌面应用改成「本地服务 + 浏览器窗口」架构，exe 体积与运行复杂度明显上升，且需要引入前端构建链。

**只买 QFluentWidgets 商业授权。** 能同时解决 GPL 约束。不选（当前）：内部使用无分发诉求，先不产生费用；等有对外交付需求时再评估。

## Consequences

**收益：** 控件观感与交互（按钮图标、密码框眼睛、表格、下拉弹层、进度条）一步到位；UI 代码量与样式维护成本下降；组件库自带主题色与深浅色能力，后续换色成本低；核心逻辑未受影响。

**代价：** 引入 GPLv3 依赖，仅限内部使用，对外交付受限；exe 体积与打包复杂度增加（需排除其它 Qt 绑定，构建耗时变长）；深度定制仍受组件库 API 限制；`app/ui/theme.py` 与自绘图标方案成为历史，相关旧测试断言调整了 1 项。
