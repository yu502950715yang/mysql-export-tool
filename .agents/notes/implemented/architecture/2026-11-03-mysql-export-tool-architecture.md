# Agent Note: MySQL 导出工具的分层与排除语义

Status: implemented

## Problem

旧脚本 `export_data_exclude_logs.py` 把连接信息与排除规则硬编码在源码里，运行需要 Python 环境；更关键的是被排除的表被整体跳过，交付出去的库缺少这些表的建表语句，导入方拿不到完整结构。产品化目标是：Windows 单文件 exe、连接与排除可配置、可勾选任意库与表、**被排除的表只保留建表语句、不导出数据**。

## Decision

工具按三层拆分，依赖单向向下：

- `app/core`：模型、config + DPAPI、字面量编码、分类、SQL 写出、runner 编排；零 Qt 依赖，可单测、可被 CLI 复用
- `app/dialects`：`Dialect` 抽象（连接、列库表、DDL、流式读取、字面量）+ `MySQLDialect`（PyMySQL）+ `MemoryDialect`（自检与单测，不连真实库）
- `app/ui`：PySide6 主窗口 + QThread worker；GUI 与 CLI 共用 `core.runner`

关键语义（must 保持）：

- **排除表 = 仅结构**：输出 `DROP TABLE IF EXISTS` + `CREATE TABLE`，文件中不得出现该表的任何 INSERT；视图被排除则不输出（视图无数据可导）
- **排除双通道**：表清单未勾选（按库持久化到 `config.json` 的 `databases.<db>.exclude_tables`）+ 正则（大小写不敏感、`re.match`，`exclude_regexes`）；正则优先于勾选
- **每库一个 `<db>.sql`**：表在前、视图在后，文件尾 `SET FOREIGN_KEY_CHECKS=1;`；排除表清单写入文件头注释
- **密码**只以 Windows DPAPI 密文落盘（`password_dpapi`）；`config.json` 优先 exe 同目录、`%APPDATA%` 回退，原子写，损坏备份 `.bak` 后自愈
- **视图定义**取 `information_schema.VIEWS.VIEW_DEFINITION` 而非 `SHOW CREATE VIEW`，避免 `DEFINER` 导致换账号导入失败
- **导出流式**：`SSCursor` + `fetchmany` 逐批写盘；进度按「库 / 表 / 已导行数」，不把 `TABLE_ROWS` 估算当分母
- **`--selftest`** 用 `MemoryDialect` 跑真实写出链路，断言「排除表有 CREATE、无 INSERT」，作为 exe 打包冒烟；GUI 与 CLI 均不为自检启动真实数据库

## Affected repositories

- `mysql-export-data` 分支 `main` commits `041e5f8` `59c2900`

## Alternatives considered

**继续给旧脚本套配置文件 + PyInstaller。** 改动最小、几乎零新代码。不选：同事需要勾选表与配置排除表，手改配置文件不可接受，需求明确要图形界面。

**包装 mysqldump / mysqlpump。** 成熟、快，支持 `--ignore-table`。不选：目标机需安装 MySQL 客户端；更关键的是 `--ignore-table` 会让排除表连建表语句都没有，与核心需求相反；也无法提供库表勾选、进度与取消。

**tkinter/ttk 界面。** 零第三方依赖、exe 约 15 MB、启动快。不选：表清单勾选、进度与错误提示的观感弱，本次是交付同事、要求友好易用的场景。

**每条 INSERT 合并多行（multi-row insert）。** 体积更小、导入更快。不选：单行 INSERT 便于阅读、按行恢复与中断，且与现有脚本行为一致；大表性能由流式读取与分批写盘保证。

**视图用 `SHOW CREATE VIEW` 保留 ALGORITHM / SQL SECURITY。** 定义更完整。不选：结果含 `DEFINER`，导入到不同账号会失败；改用 information_schema 的定义。

## Consequences

**收益：** 单 exe 交付、非技术同事可直接使用；排除表结构随导出文件交付，导入方得到完整库结构；核心层与界面解耦，`MemoryDialect` 让 94 项测试不需要真实数据库；密码加密与配置自愈；新增数据库类型只需增加一个 `app/dialects/xxx.py`。

**代价：** 只实现 MySQL/MariaDB（其它方言仅留接口）；PySide6 onefile 体积与启动时间明显大于 tkinter；DPAPI 密文换机器或换 Windows 用户后必须重输密码；单行 INSERT 使文件体积偏大；模态对话框路径（错误 / 报告 / 预览弹窗）未纳入单测，需人工验收覆盖。
