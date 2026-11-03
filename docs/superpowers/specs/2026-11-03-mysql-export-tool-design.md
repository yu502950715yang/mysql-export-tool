# MySQL 数据库导出工具（GUI 桌面程序 + 单文件 exe）设计文档

- 日期：2026-11-03
- 状态：已与用户确认（第 1–4 节设计逐节批准），待评审后进入实施计划
- 来源需求：基于旧版命令行导出脚本衍生 —— 需要一个 exe 程序，能导出任意数据库的数据；数据库信息可配置；排除的表可配置；**被排除的表要保留建表语句、不保留数据**。
- 已确认的关键决策（与用户逐题确认）：
  1. 数据库范围：**MySQL 优先，架构预留多数据库扩展**
  2. 交互形态：**图形界面（GUI）+ 打包 exe**
  3. 排除表配置：**表清单勾选 + 正则规则**
  4. 产物组织：**每库单个 `.sql` 文件**
  5. 密码存储：**config.json + Windows DPAPI 加密**
  6. 结构范围：**表 + 视图**
  7. 打包形态：**单文件 exe（PyInstaller onefile）**
  8. 使用场景：**团队/同事交付，界面友好易用**
  9. 技术方案：**PySide6 桌面 GUI（方案 A）**

---

## 1. 背景与目标

旧版命令行导出脚本（已从仓库移除）的功能是：连接 MySQL，按库导出 `CREATE TABLE + INSERT`，默认排除日志类表（脚本会直接跳过被排除表，连建表语句都不输出），可选导出 CSV。它的问题：数据库连接信息硬编码在脚本顶部、排除规则写死在代码里、需要 Python 环境、非技术人员不可用。

本工具目标：把该能力产品化成一个**双击即用的 Windows 单文件 exe**：

- 任意 MySQL/MariaDB 服务器，连接信息在界面配置并持久化（多套配置可切换）
- 连上服务器后勾选任意数据库、任意表
- 排除的表可"取消勾选"或"正则匹配"得到；**排除表仍输出 `DROP TABLE` + `CREATE TABLE`，但不输出任何 INSERT**
- 导出结果每库一个 `.sql`，可直接 `mysql < xxx.sql` 导入
- 无需安装 Python，拷一个 exe 即可运行

## 2. 术语

| 术语 | 含义 |
| --- | --- |
| 导出表 | 勾选且未被正则命中的表：输出建表语句 + 全部数据 |
| 排除表 | 未勾选或被正则命中的表：只输出建表语句（含 DROP），**无数据** |
| 仅结构（排除表） | 上述排除表的输出语义 |
| Profile | 一套数据库连接配置（主机/端口/账号/密码/库及排除规则） |
| Dialect | 数据库方言适配层，当前只实现 MySQL |
| dry-run / 预览 | 只做库表发现与分类统计，不写任何文件 |

## 3. 非目标（明确不做）

- 不支持 PostgreSQL / SQL Server / Oracle 等（只留 Dialect 接口，当前 UI 数据库类型固定 MySQL）
- 不导出触发器、存储过程、函数、事件
- 不导出 CSV（本工具只输出 SQL；旧脚本的 CSV 能力不迁移）
- 不做断点续传、增量/差异导出、定时导出、网络传输
- 不做导出加密、压缩（用户可自行对输出目录打包）
- 不做数据脱敏/敏感字段过滤
- 不提供旧脚本配置的导入迁移（旧脚本配置硬编码在源码里，无落盘配置文件）

## 4. 需求清单

### 4.1 功能需求

- FR-1 多套连接配置可新建、复制、重命名、删除、切换、保存；密码经 DPAPI 加密后落盘，界面掩码显示
- FR-2 测试连接：给出成功/失败原因（认证失败、网络不可达、超时等）
- FR-3 连接成功后刷新数据库列表（默认隐藏系统库，可显示），多选勾选要导出的库
- FR-4 每个库展示表与视图清单（名称、类型、估算行数）；表可勾选/取消/全选/反选
- FR-5 正则排除：多行文本，一行一条，大小写不敏感，实时校验并预览命中影响
- FR-6 排除表输出建表语句、不输出数据；视图输出建视图语句
- FR-7 每库输出单个 `.sql` 文件，内容可直接导入
- FR-8 导出前预览（dry-run）：显示每库表数、估算行数、排除表清单与命中规则
- FR-9 导出进度（库/表/行数/耗时）与可取消；完成后给汇总报告并可打开输出目录
- FR-10 导出日志同时显示在界面并落盘为文件
- FR-11 每个库的排除设置随配置保存，下次打开恢复
- FR-12 CLI 入口：支持 `--selftest`、`--dry-run`、`--config`、`--profile`、`--outdir` 等，便于自动化与排障

### 4.2 非功能需求

- NFR-1 大表内存恒定：SSCursor 流式 + 分批写盘，不整表载入内存
- NFR-2 单库/单表失败不影响其它库表；已写文件保持可导入
- NFR-3 UI 全程不阻塞（网络与导出在后台线程）
- NFR-4 配置原子写入，损坏自愈（备份 `.bak` 后重建）
- NFR-5 日志与界面不出现明文密码；配置文件不含明文密码
- NFR-6 单文件 exe 在 Windows 10/11 x64 无 Python 环境直接运行
- NFR-7 核心引擎零 Qt 依赖，可单测、可被 CLI 复用

## 5. 总体架构

### 5.1 分层

```
┌────────────┐   ┌────────────┐
│  GUI (Qt)  │   │  CLI       │      表现层（薄）
└─────┬──────┘   └─────┬──────┘
      └────────┬───────┘
        ┌──────▼───────┐
        │   runner     │             编排层：连接→逐库→进度/取消→报告
        └──────┬───────┘
   ┌───────────┼────────────┬──────────────┐
   │ introspect│ classify   │ writer_sql   │   核心层（纯 Python，零 Qt）
   │ literal   │ config     │ secret       │
   └───────────┼────────────┴──────────────┘
        ┌──────▼───────┐
        │  dialects    │             方言层：base 接口 + mysql 实现
        └──────────────┘
```

依赖方向单向向下；`core` 不 import `ui`；`dialects` 不被 `ui` 直接调用。

### 5.2 目录结构

```
mysql-export-data/
├─ app/
│  ├─ __init__.py            # __version__ = "0.1.0"
│  ├─ main.py                # 入口：无参→GUI，带参→CLI
│  ├─ cli.py                 # argparse：--selftest/--dry-run/--config/--profile/--outdir/--version
│  ├─ core/
│  │  ├─ models.py           # Profile/DatabaseConfig/ExcludeRule/ExportOptions/TableInfo/ExportReport
│  │  ├─ config.py           # 读写/校验/迁移/原子写/坏文件自愈/路径解析
│  │  ├─ secret.py           # DPAPI 加解密（ctypes，Win32 CryptProtectData/CryptUnprotectData）
│  │  ├─ classify.py         # 导出/排除判定与原因
│  │  ├─ literal.py          # SQL 字面量与字符串清洗
│  │  ├─ plan.py             # 由 profile + 勾选库生成导出计划
│  │  ├─ writer_sql.py       # .sql 文件写出
│  │  ├─ runner.py           # 导出编排、进度回调、取消、统计、报告
│  │  └─ errors.py           # 异常分类与中文消息
│  ├─ selftest.py            # --selftest 内置自检（内存方言，不连库）
│  ├─ dialects/
│  │  ├─ base.py             # Dialect 抽象接口 + DialectError
│  │  ├─ mysql.py            # MySQLDialect（PyMySQL）
│  │  └─ memory.py           # MemoryDialect：--selftest 与单测用，不连真实库
│  └─ ui/
│     ├─ main_window.py      # 主窗口与交互
│     ├─ widgets.py          # 表清单、进度组件、日志区
│     ├─ dialogs.py          # 错误详情/导出完成/覆盖确认/正则编辑
│     └─ workers.py          # QThread worker + 信号
├─ tests/
├─ build/                    # mysql-export-tool.spec、build.ps1、version_info.txt、entry.py、make_icon.py、app.ico
├─ docs/superpowers/specs/
├─ requirements.txt
├─ pyproject.toml
├─ README.md
└─ .gitignore
```

### 5.3 Dialect 接口（多库扩展预留）

```python
class Dialect(ABC):
    names: set[str] = {"mysql"}
    label: str = "MySQL"

    def connect(self, profile) -> None: ...
    def close(self) -> None: ...
    def ping(self) -> str: ...                       # 返回服务器版本串
    def list_databases(self, include_system: bool) -> list[str]: ...
    def list_tables(self, db: str) -> list[TableInfo]: ...   # 表与视图，含估算行数
    def create_table_sql(self, db: str, table: str) -> str: ...
    def drop_table_sql(self, table: str) -> str: ...
    def create_view_sql(self, db: str, view: str) -> str: ...
    def drop_view_sql(self, view: str) -> str: ...
    def stream_rows(self, db: str, table: str, batch: int) -> Iterator[tuple[list[str], list[tuple]]]: ...
    def literal(self, value, options: ExportOptions) -> str: ...


def quote_ident(name: str) -> str: ...   # 标识符加引号（MySQL 用反引号）
```

`drop_*_sql` 返回带分号的完整语句；`create_*_sql` 返回不带结尾分号的 DDL，由写出层补 `;`。
实现上 `quote_ident` 定义在 `app/core/literal.py`，`dialects/base.py` 重新导出（避免 `core` 反向依赖 `dialects`）。

`dialects/registry.py` 或 `base.DIALECTS` 按名字注册；GUI 里数据库类型是只读下拉，但配置中保留 `dialect` 字段。调用未实现方言抛出 `DialectError("暂不支持：xxx")`。

## 6. 配置模型

### 6.1 存放位置与解析顺序

1. 若 `--config` 指定 → 用它
2. 否则 exe 同目录 `config.json`（便携）
3. 若该目录不可写 → `%APPDATA%\MysqlExportTool\config.json`

界面顶部显示实际生效路径，点击可打开所在目录。

### 6.2 Schema（version 1）

```jsonc
{
  "version": 1,
  "active_profile": "dev",
  "ui": { "last_outdir": "D:/export", "show_system_dbs": false },
  "profiles": [
    {
      "name": "dev",
      "dialect": "mysql",
      "host": "127.0.0.1",
      "port": 33061,
      "user": "demo",
      "password_dpapi": "BASE64…",          // DPAPI 密文，不存明文
      "charset": "utf8mb4",
      "connect_timeout": 10,
      "databases": {                         // 按库记忆排除配置
        "demo_shop_system": {
          "exclude_tables": ["sys_oper_log"],
          "exclude_regexes": [".*_log$", "^tmp_.*$"]
        }
      },
      "selected_databases": ["demo_shop_system", "demo_shop"],  // 上次勾选的库
      "options": {
        "escape_unicode": true,
        "drop_before_create": true,
        "include_views": true,
        "batch_size": 1000,
        "filename_timestamp": false
      }
    }
  ]
}
```

规则：

- 未出现在 `databases` 里的库：默认全部勾选导出、无排除规则
- `selected_databases`：上次勾选要导出的库，GUI 启动后恢复勾选状态；CLI `--dry-run` 未指定 `--databases` 时默认使用它
- `exclude_tables`：精确表名（大小写不敏感比较）
- `exclude_regexes`：正则列表，逐表 `re.match` 且 `re.IGNORECASE`
- 读取时校验字段类型；缺省字段用默认值补齐；`version` 小于当前则跑迁移函数（当前只有 1，预留）

### 6.3 原子写与自愈

- 保存：写 `config.json.tmp` → fsync → `os.replace` 覆盖
- 读取失败（JSON 损坏/类型错误）：把坏文件重命名为 `config.json.bak-<时间戳>`，生成空配置（一个空白 profile），界面提示日志路径
- 密码加解密失败（换机器/换用户导致 DPAPI 解不开）：该 profile 密码视为空，界面提示"请重新输入密码"，不崩溃

### 6.4 DPAPI 细节

- `CryptProtectData(data, None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN)` → base64 存 `password_dpapi`
- 解密用 `CryptUnprotectData`，失败抛 `SecretError`，上层转成"密码需重新输入"
- `secret.py` 仅 Windows 可用；非 Windows 平台（仅开发测试）抛 `SecretError("仅支持 Windows")`

## 7. 导出语义（核心行为）

### 7.1 连接

- PyMySQL：`host/port/user/password/database=None/charset/connect_timeout`，`autocommit=True`
- 测试连接 = `SELECT VERSION()`，返回版本串显示在状态栏
- 连接时不指定 `database`，导某库时用完全限定名 `` `db`.`table` `` 或切换库（实现取简单可靠者：SQL 里带库名前缀）

### 7.2 库/表/视图发现

- 库：`SHOW DATABASES`；`include_system=false` 时排除 `information_schema/mysql/performance_schema/sys`
- 表：`information_schema.TABLES WHERE TABLE_SCHEMA=%s`，列 `TABLE_NAME/TABLE_TYPE/TABLE_ROWS`，按类型、名称排序
- 视图：同源 `TABLE_TYPE='VIEW'`；视图定义取 `information_schema.VIEWS.VIEW_DEFINITION`（不含 DEFINER、不含 SQL SECURITY）
- 估算行数仅用于展示与预览，不作为进度分母

### 7.3 分类规则

对当前库的表清单，逐表判定：

1. 若表名匹配任一 `exclude_regexes` → 排除（原因：命中正则 `xxx`）
2. 否则若在 `exclude_tables` 中 → 排除（原因：勾选排除/历史配置）
3. 否则 → 导出

GUI 上"未勾选"等价于把表名加入 `exclude_tables` 保存；勾选则移除。视图单独按 `include_views` 开关 + 视图勾选状态决定是否输出（视图无数据，默认全部输出）。

### 7.4 输出文件与内容

- 目录：用户选择（默认上次目录；首次为 exe 同目录 `exports/`，不可写则 `%USERPROFILE%\Documents\MysqlExportTool\exports`）
- 文件名：`<db>.sql`；`filename_timestamp=true` 时 `<db>_<yyyyMMdd_HHmmss>.sql`
- 已存在且未开时间戳 → 导出前弹窗确认覆盖（取消则中止本次）

文件结构（单文件，顺序固定）：

```sql
-- database `demo_shop_system` data export
-- generated by MysqlExportTool v0.1.0 at 2026-11-03 10:30:00
-- excluded tables (structure only): sys_oper_log, sys_logininfor
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

-- ----------------------------
-- table `sys_user` (export: data)
-- ----------------------------
DROP TABLE IF EXISTS `sys_user`;
CREATE TABLE `sys_user` (...);
INSERT INTO `sys_user` (`id`,`name`) VALUES (1,'a');
-- table `sys_user` rows: 1

-- ----------------------------
-- table `sys_oper_log` (excluded: structure only)
-- ----------------------------
DROP TABLE IF EXISTS `sys_oper_log`;
CREATE TABLE `sys_oper_log` (...);

-- ----------------------------
-- view `v_sys_user`
-- ----------------------------
DROP VIEW IF EXISTS `v_sys_user`;
CREATE VIEW `v_sys_user` AS SELECT ...;

SET FOREIGN_KEY_CHECKS=1;
```

- 所有建表在某表自己的段内完成；视图统一放在所有表之后
- `drop_before_create=false` 时不输出 `DROP ...`
- 排除表段内不得出现 `INSERT`
- 排除表清单写入文件头注释，便于核对

### 7.5 SQL 字面量（沿用旧脚本策略）

| 值 | 输出 |
| --- | --- |
| `None` | `NULL` |
| `bytes` 非空 | `_binary 0x<hex>` |
| `bytes` 空 | `_binary ''`（MySQL 8 下 `_binary 0x` 是语法错误） |
| ASCII `str` | `conn.escape(v)` 转义后的字符串 |
| 非 ASCII `str`（`escape_unicode=true`） | `_utf8mb4 0x<utf-8 hex>` |
| 非 ASCII `str`（`escape_unicode=false`） | `conn.escape(v)` |
| 其他（int/float/Decimal/date…） | `conn.escape(v)` |
| 代理字符等非法 UTF-8 | 先 `encode('utf-8','replace').decode()` 清洗，再按上表 |

列名、表名统一 `` `反引号` `` 包裹并转义内部反引号。

### 7.6 流式读取与写盘

- `SSCursor` + `fetchmany(batch_size)`，每批逐行拼 INSERT 写入文件
- 写入用文本模式：`utf-8`、`newline='\n'`（保证跨平台导入一致）
- 每表结束写 `-- table xxx rows: N`
- 单行 INSERT（与旧脚本一致，便于阅读和粗粒度恢复）

### 7.7 取消与错误

- 取消：`threading.Event`，在每个批次/每张表边界检查；触发后补齐 `SET FOREIGN_KEY_CHECKS=1;` 并关闭文件，报告状态 `cancelled`
- 单库连接/发现失败：记错误，跳过该库，继续下一库
- 单表读取失败：该表写建表语句（能拿到时）、跳过数据、记错误，继续后续表
- 建表语句获取失败：记错误并跳过该表结构（不影响数据继续？——取不到结构时不写数据，避免无法导入；记错误）
- 视图定义取不到（权限不足）：记错误、跳过该视图
- 磁盘不可写/空间不足：中止本次导出，错误消息含路径
- 报告结构：`ExportReport{status, started_at, elapsed, databases:[{db, path, tables:[{name, kind, rows, error}], errors:[]}], total_tables, total_rows}`

### 7.8 进度

- 库级：已完成库数/总库数
- 表级：当前库内已完成表数/表数
- 当前表已导行数（累计），以及每表结束的实际行数
- 信号频率：每批一次（约 1000 行或每表结束），避免 UI 高频刷新

## 8. GUI 设计

### 8.1 主窗口布局（单窗口，约 1000×760，可缩放）

1. **顶部工具条**：配置文件路径（可点击）+ Profile 下拉 + 新建/复制/重命名/删除 + 保存配置 + 关于
2. **连接区（QGroupBox）**：数据库类型（MySQL 只读）、主机、端口、用户名、密码（掩码）、显示密码、测试连接、状态标签
3. **库区**：「刷新库表」按钮、显示系统库复选、库列表（多选 QListWidget 或带复选框的表格）
4. **表清单区**（库列表中"当前高亮"的库，高亮与勾选相互独立）：
   - 工具条：全选/全不选/反选、正则排除按钮、状态文案"表 N 个，导出 X，仅结构 Y"
   - `QTableWidget`：勾选 | 表名 | 类型 | 估算行数 | 说明（命中正则/仅结构）
   - 视图行标 `VIEW`，勾选=输出视图定义（默认勾选）
5. **输出设置区**：目录（选择按钮 + 路径显示）、文件名带时间戳、不输出 DROP、中文转十六进制、批量大小（QSpinBox）
6. **操作按钮**：预览（dry-run）、开始导出
7. **进度/日志区**：总进度条、当前任务文本、已导行数/耗时、进度条取消按钮、日志 QPlainTextEdit（只读、可复制）
8. **状态栏**：当前配置文件名、目标库数、最近消息

### 8.2 交互流程

1. 启动 → 读配置 → 显示 active profile → 不自动连接
2. 填/改连接 → 测试连接 → 成功后「刷新库表」
3. 勾选库 → 表清单加载高亮库的表；该库已有保存的排除规则则恢复为对应勾选状态，从未配置过的库默认全选导出
4. 调整勾选/正则 → 状态文案实时更新
5. 预览 → 后台 dry-run → 弹窗展示每库分类统计（取消不写文件）
6. 开始导出 → 保存配置 → 覆盖确认 → 后台导出 → 进度/日志实时 → 完成弹报告
7. 导出中：禁用配置区与连接区、启用取消、关窗弹确认
8. 取消/失败：报告区分成功、失败、取消；「打开输出目录」「复制日志路径」

### 8.3 线程与信号

- `ConnectionWorker(QThread)`：测试连接、刷新库表
- `ExportWorker(QThread)`：执行 `runner.export()`，信号：
  - `sig_log(str)`
  - `sig_progress(ProgressInfo)` — db 下标、表名、已导行数、耗时
  - `sig_finished(ExportReport)`
  - `sig_error(str, str)` — 摘要 + 详情
- 取消通过 `runner.cancel_event` 传入
- worker 内部异常一律捕获转 `sig_error`，禁止让异常逃逸导致线程崩溃

### 8.4 校验规则

- 主机/用户/密码/端口非空；端口 1–65535
- 正则逐条编译，非法立即标红并阻止预览/导出
- 未勾选任何库时禁用预览/导出并提示
- 输出目录不存在 → 自动创建（失败提示）；路径不可写提示

## 9. CLI 接口

```
MysqlExportTool.exe [--selftest] [--config PATH] [--profile NAME]
                    [--dry-run] [--outdir DIR] [--databases a,b]
                    [--exclude-tables a,b] [--exclude-regex r1,r2]
                    [--format sql] [--version]
```

- `--selftest`：构造核心对象 + 用一个假 Dialect 执行 mini 导出到临时目录并校验内容，打印 `SELFTEST OK`，退出码 0/1；**不启动 GUI**（打包后冒烟用）
- `--dry-run`：用指定 profile 连库发现并打印分类统计，不写文件
- 无参数：启动 GUI
- CLI 与 GUI 共用 `core.runner`，保证行为一致

## 10. 错误处理与日志

- `errors.py` 定义 `AppError`（用户可读 message + 技术 detail + hint），映射 PyMySQL 常见异常：
  - `OperationalError 1045` → 用户名或密码错误
  - `OperationalError 2003/2013` → 无法连接目标主机/端口，检查网络与防火墙
  - `OperationalError 1049` → 库不存在
  - `OperationalError 1044/1142` → 权限不足
  - `OSError`/磁盘错误 → 输出目录不可写或空间不足
  - 其余 → 原始异常摘要
- 日志：`logging` + 文件 handler，路径 `<outdir>/export-<yyyyMMdd_HHmmss>.log`；格式 `时间 级别 消息`；不记录密码、不记录数据内容；错误写 traceback 到日志但界面只显示摘要
- 界面错误弹窗：摘要 + 「详情」折叠区 + 日志路径

## 11. 测试策略

### 11.1 单元测试（pytest，零数据库依赖）

- `test_literal.py`：NULL、空/非空 bytes、ASCII 引号与反斜杠、中文转十六进制、`escape_unicode=false`、UTF-8 代理字符清洗、数字/日期原样
- `test_classify.py`：正则命中（大小写不敏感）、精确排除、默认导出、视图不参与数据、原因文案
- `test_config.py`：默认值补齐、坏 JSON 自愈并生成 `.bak`、原子写（写 tmp 再 replace）、profile 增删改、未知字段容忍
- `test_secret.py`：DPAPI 往返（`pytest.mark.skipif` 非 Windows）、解密失败转 `SecretError`
- `test_writer.py`：用 FakeDialect：
  - 排除表段存在 `CREATE TABLE` 且**不含 `INSERT`**
  - 导出表有 INSERT 且行数统计正确
  - 视图出现在所有表之后
  - 文件头含排除表清单；`drop_before_create=false` 时无 DROP
  - 尾部 `SET FOREIGN_KEY_CHECKS=1;`
- `test_runner.py`：FakeDialect 模拟正常/取消/单表异常/单库连接失败；校验 `ExportReport` 状态、错误聚合、进度回调序列

### 11.2 GUI 冒烟

- `python -m app --selftest`（核心冒烟）
- `QT_QPA_PLATFORM=offscreen` 下构造 MainWindow、断言关键控件存在、关闭（CI 可用）
- 打包后：`dist\MysqlExportTool.exe --selftest` 退出码 0

### 11.3 集成测试（可选，环境变量开关）

- 需 `MYSQL_TEST_HOST/PORT/USER/PASSWORD` 才执行，否则 `pytest.skip`
- 构造临时库：2 库、3 表（含 1 排除表）、1 视图；导出后断言输出；再用一次性编译/导入（若测试账号允许建库）校验可导入

### 11.4 验收基准（人工验收清单）

1. 双击 exe 启动，无 Python 环境
2. 配置连接 → 测试连接成功 → 刷新库表
3. 勾选库、取消一张表、加正则 `^tmp_.*$` → 预览显示分类正确
4. 导出完成：每库一个 `.sql`；被排除表只有 DROP+CREATE，无 INSERT；视图在表之后
5. 把导出文件导入空库成功，行数一致（与源库 `COUNT(*)` 抽查）
6. 取消导出 → 报告"已取消"，文件可导入
7. 关闭再开，配置与排除规则仍在，密码免输入（同机同用户）
8. 日志文件生成于输出目录，无密码明文

## 12. 打包与交付

- PyInstaller 6.19，`--onefile --windowed`，`--name MysqlExportTool`，图标 + `version_info.txt`（产品名、版本 0.1.0、公司/版权占位）
- spec 中 `excludes`：`PySide6.QtWebEngineCore/QtWebEngineWidgets/QtQml/QtQuick/QtQuickWidgets/Qt3D*/QtMultimedia/QtBluetooth/QtCharts/QtDataVisualization/QtSql/QtTest`、`tkinter` 等；`hiddenimports` 按需
- 体积目标 ≤ 80 MB（预期 40–60 MB）
- `build/build.ps1`：清理 `build/ dist/` → `pyinstaller build/mysql-export-tool.spec --clean --noconfirm` → 输出 `dist/MysqlExportTool.exe` 的 SHA256 → 运行 `--selftest` 冒烟，失败则非零退出
- 交付物：`dist/MysqlExportTool.exe`、`README.md`（中文：配置说明、使用步骤、密码 DPAPI 跨机限制、常见错误、许可）、`THIRD_PARTY_LICENSES`（PySide6 LGPL v3、PyMySQL MIT）
- 兼容：Windows 10/11 x64；Python 3.13 + Anaconda 环境构建（环境已就绪：PyInstaller 6.19、PySide6 6.9.2、PyMySQL 1.1.2、pytest 8.3.4）
- 不签名、不做安装包（单文件 exe 分发）；文档写明杀软误报处理建议

## 13. 实施拆分（供 writing-plans 展开）

1. 仓库初始化（git init、.gitignore、requirements、pyproject、README 骨架）
2. 核心层：models/literal/errors/config/secret + 单测
3. 方言层：Dialect 基类 + MySQLDialect（introspect + DDL + stream） + FakeDialect 测试夹具
4. 写出层：classify + writer_sql + 单测
5. 编排层：runner（进度/取消/错误/报告）+ 单测
6. CLI + main 入口 + `--selftest`
7. GUI：主窗口、表清单、正则编辑、workers、进度/日志、报告
8. 集成与 GUI 冒烟、人工验收
9. 打包：spec、build.ps1、exe 冒烟、README/许可
10. 收尾：intent-notes 决策笔记、最终 diff 复核

## 14. 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| PySide6 onefile 体积大/启动慢 | 交付观感 | spec 剔除无关 Qt 模块；目标 ≤80 MB；文档说明首次启动 2–4 秒 |
| 目标 MySQL 版本/字符集差异导致导入失败 | 数据可用性 | 建表语句原样导出；`SET NAMES utf8mb4`；`FOREIGN_KEY_CHECKS=0`；验证导入 |
| 视图定义含 DEFINER/权限依赖 | 导入报错 | 用 `information_schema.VIEWS.VIEW_DEFINITION`，不写 DEFINER |
| 大表导出时间长、被误以为卡死 | 体验 | 进度条按表/行实时刷新 + 日志 + 可取消 |
| DPAPI 换机解不开密码 | 体验 | 文档说明并给出"重新输入密码"路径 |
| 单文件 exe 被杀软误报 | 分发 | 文档说明；必要时提供 onedir 备选（当前不做） |
| 无可用 MySQL 环境做集成测试 | 质量 | FakeDialect 单测覆盖逻辑；集成测试按环境变量开关，默认跳过 |

## 15. 开放问题

无。所有关键决策已与用户确认；若实施中发现隐藏复杂度（如需支持多库方言的真实现），按流程升级并回到设计确认。

---

## 16. 实施备注（实现后补充，2026-11-03）

以下为实现定稿的细节；与上文不一致之处以本节为准。

- `quote_ident` 定义在 `app/core/literal.py`，由 `app/dialects/base.py` 重新导出（避免 core 反向依赖 dialects）。
- 新增模块：`app/core/plan.py`（profile + 勾选库 → 导出计划）、`app/dialects/memory.py`（自检/单测用内存方言）、`app/selftest.py`（`--selftest`）、`app/__main__.py`（`python -m app`）。
- workers 实际为 5 个：`PingWorker` / `DatabasesWorker` / `TablesWorker` / `PreviewWorker` / `ExportWorker`；全部以主窗口为 parent，关闭窗口时统一等待运行中线程。
- GUI 的 `include_views` 固定为 True：视图默认全部导出，取消勾选或命中正则才不输出；`ExportOptions.include_views` 字段保留给 CLI/API 使用。
- CLI `--outdir` 为预留参数、当前不生效；`--dry-run` 不写任何文件，仅连接数据库发现库表并打印分类统计。
- `config.json` 的 profile 增加 `selected_databases`（上次勾选的库），CLI `--dry-run` 未指定 `--databases` 时使用它。
- 导出期间主窗口传 `copy.deepcopy(profile)` 快照给后台线程，避免界面修改连接信息污染后续库连接。
- 测试基线 94 项（核心 43 + CLI/自检 5 + 方言/写出/runner 26 + GUI 20），`python -m pytest -q` 全绿。

---

## 17. 界面简化改版（2026-11-03 追加）

初版界面把功能全量平铺（每块带说明、按钮成排、日志与进度常显），反馈「啰嗦、体验不好」。改版遵循「三步一屏」：连接 → 选库表 → 导出。

- **布局**：顶部应用栏（产品名/版本、配置下拉、配置菜单、关于）→ 连接卡片（主机/端口/用户名/密码/眼睛/连接，右侧状态徽标）→ 左右分栏（左数据库列表、右表清单，可拖动分隔）→ 底部操作栏（输出目录、浏览、导出设置、预览、开始导出；展开区含导出设置、进度、状态行、日志）。
- **渐进披露**：导出设置（时间戳/DROP/编码/批量）与日志默认折叠；进度仅在导出时出现；未连接、未选库时显示空态引导而非空框。
- **配置**：新建/复制/重命名/删除/保存/打开配置目录收进顶部「配置」菜单，配置文件路径不再常显。
- **排除语义可视化**：正则命中的表在清单中锁定为未勾选、灰显并标注「命中正则（仅结构）」；未勾选=仅结构，勾选=导数据；统计行按分类结果给出「表 / 导出 / 仅结构 / 视图」。
- **设计令牌**：由 `ui-design-system` 生成（主色 `#2563EB`、modern、8pt 间距、8/10px 圆角、微软雅黑 UI），实现于 `app/ui/theme.py`（QSS + QPainter 图标）。QSS 无法画图形，运行时在临时目录生成 `check-white.png`（勾选）与 `chevron-down.png`（下拉箭头），供 `QListWidget::indicator`、`QCheckBox::indicator`、`QComboBox::down-arrow` 使用，避免原生子控件残留系统主题色块。
- **兼容性**：核心导出 API 与数据模型不变；`MainWindow` 保留既有属性名/方法名。原 95 项测试中 3 项因界面结构调整（顶部路径标签改为菜单）更新断言，现 **97 项全绿**。
- **截图**：`docs/design/capture_ui.py`（offscreen + `QT_QPA_FONTDIR` 指定系统字体）生成 `ui-empty.png`、`ui-loaded.png`、`ui-expanded.png`。


---

## 18. UI 技术栈替换为 QFluentWidgets（2026-11-03 追加）

自绘 QSS 主题在控件细节上仍达不到要求（下拉框/勾选框/表格/按钮反复修原生残影），用户对组件质感不满意。对比 QFluentWidgets、QML Material、自绘三版 demo 后，在「仅公司内部使用」前提下选用 **PySide6-Fluent-Widgets 1.11.3**（GPLv3/商业双许可）。

- `app/ui` 全部控件换成 QFluentWidgets 组件（Card/ElevatedCardWidget、PrimaryPushButton、LineEdit、PasswordLineEdit、ComboBox、SpinBox、CheckBox、ListWidget、TableWidget、ProgressBar、PlainTextEdit、RoundMenu 等）；`app/ui/theme.py` 删除，不再手写设计令牌与 QSS。
- 主窗口结构与交互保持不变：三步一屏、折叠导出设置/日志、正则命中行锁定、状态徽标、空态提示、导出快照与线程等待。
- 页面浅灰背景由根 QWidget 一行样式提供（唯一保留的内联样式），其余样式交给组件库主题。
- 打包：PyInstaller spec 增加 `PyQt5/PyQt6/PySide2/sip` 排除项——构建机 Anaconda 同时安装 PyQt5 会触发 PyInstaller「multiple Qt bindings」错误。
- 许可：QFluentWidgets 为 GPLv3，仅内部使用；`README.md` 与 `THIRD_PARTY_LICENSES` 已更新，对外交付前需商业授权或替换 UI 层。
- 测试：97 项全绿（仅主题断言改为「导出按钮是 QFluentWidgets 的 PrimaryPushButton」）。界面截图已用新版重拍。


**构建备注（2026-11-03 实测）：** PyInstaller 必须用项目 .venv 构建（uild/build.ps1 已默认优先 .venv）。用 Anaconda 构建时，QFluentWidgets 对 numpy 的可选导入会把 Anaconda 的 MKL 全家桶打进 exe（273 MB）；换 .venv 后为 **53.1 MB**，构建约 47 秒，--selftest 与 GUI 冒烟均通过。打包仍需排除 PyQt5/PyQt6/PySide2（构建机装了多套 Qt 绑定），并保留 QtSvg/QtSvgWidgets（QFluentWidgets 实际依赖）。


---

## 19. 多库选表交互改版（2026-11-03 追加）

用户反馈「左侧选完多个库后，右侧只看一个库的表、没发快速排除」。改为：

- 右侧表清单按**已勾选的数据库分 Tab**（QFluentWidgets.TabBar），勾选几个库就有几个 Tab；左侧点击库会切到对应 Tab，Tab 切换无需重新点击左侧列表。Tab 不显示关闭/新增按钮，避免与左侧勾选状态脱节。
- 每个 Tab 提供：**表名搜索框**、**排除选中**（多选行后一键排除）、**批量排除**（弹窗粘贴表名，可应用到所有已勾选库）、**正则**（可应用到所有已勾选库）、全选/清空。
- 表数据按库缓存（_db_tables），首次激活 Tab 时异步加载；每库的排除状态仍存入 config.json 的 databases.<db>。
- 排除语义不变：被排除的表仍输出建表语句、不导数据；正则命中的行锁定为未勾选并灰显。
- 测试：新增 Tab 切换、搜索过滤、排除选中、批量排除、批量排除对话框解析等用例，共 **102 项**全绿。


---

## 20. 表清单加载性能修复（2026-11-03 追加）

**现象：** 多库场景下右侧某个库一直显示「加载中…」。

**诊断（只读测量 32 个 schema）：** 首次逐库执行 SELECT ... FROM information_schema.TABLES WHERE TABLE_SCHEMA=? ORDER BY TABLE_TYPE, TABLE_NAME 时，有 6 个 schema 耗时 5–15 秒；复测相同查询全部 0.00s。属于 MySQL 8 元数据/统计冷缓存抖动（TABLE_ROWS 相关），原实现直接依赖该查询且没有超时，所以 UI 会长时间卡住。

**修复：**

- MySQLDialect.list_tables 改为 SHOW FULL TABLES FROM <db> 秒出表/视图清单；
- 行数估算改为独立查询，先 SET SESSION max_execution_time=1500，超时/失败直接按 0 处理，并在 inally 里重置为 0，避免影响后续数据导出；
- UI 在加载中显示「加载中…（N.N 秒）」，让等待可见；
- 实测 116/160 张表的 schema 列表耗时约 0.00–0.04 秒。


---

## 21. 表清单表头排序（2026-11-03 追加）

表与视图清单支持点击表头排序：名称、类型、估算行数、说明四列可点击，再次点击切换升/降序，表头显示排序箭头；勾选列不参与排序。

实现要点：不使用 Qt 原生 setSortingEnabled（它会打乱行号与 TableListWidget._tables 的映射，导致勾选/排除状态错位），而是在 TableListWidget 内维护排序状态并手动重排 _tables，再按“名称 → 状态 → 原因”重建行；排序前先把勾选状态同步到 _excluded，排序后恢复，保证勾选、正则锁定、搜索过滤都不受排序影响。排序状态在切换库 Tab、重新加载表清单后保持。测试新增名称/行数排序、勾选状态跨排序保持等用例，共 105 项。


---

## 22. 对话框统一 Fluent 风格（2026-11-03 追加）

导出完成、错误、正则、批量排除四个对话框此前是原生 QDialog 外观（白底直角、默认按钮），与主界面的 Fluent 卡片风格割裂。现全部改为 QFluentWidgets 的 MessageBoxBase 派生类：

- FluentDialog(MessageBoxBase) 作为基类：标题 StrongBodyLabel、内容放 iewLayout、主/次按钮固定 140px 宽并居中（避免单按钮被拉满整行）。
- 导出报告：状态摘要 + 表格式每库明细（数据库/文件/表数/行数/错误），「打开输出目录」为次级按钮，「关闭」为主按钮。
- 错误：摘要 + 建议 + 可复制详情（只保留「确定」）。
- 正则 / 批量排除：说明 + 编辑框 + 校验提示 + 「应用到所有已勾选的库」复选框 + 确定/取消；校验不通过时禁用确定。
- 测试中构造对话框需传父控件（MessageBoxBase 需要父窗口尺寸计算遮罩）；新增 docs/design/capture_dialogs.py 生成四类对话框截图 docs/design/ui-dialogs.png。


---

## 23. 日志改独立窗口，清除原生弹窗（2026-11-03 追加）

**现象：** 反复点「日志」后主页面变形：日志面板内联展开把底部导出栏撑高，主区域被压缩到极限；导出结束后进度条还常驻，窗口高度不够时内容溢出/裁切。

**修复：**

- 运行日志改为独立 Fluent 窗口 LogDialog(MessageBoxBase)：只读文本、复制/清空、关闭；导出进行中打开可实时追加日志，不再参与主窗口布局。
- 进度条只在导出期间显示，导出结束/失败后隐藏。
- 清除最后几处原生 QMessageBox，统一为 Fluent 对话框：InfoDialog（关于）、ConfirmDialog（删除配置/覆盖确认/退出确认）、TextViewDialog（导出预览，可复制）、ErrorDialog（错误，含提示/详情）。
- 测试：日志窗口、确认框、预览框用例；主窗口日志按钮改为非 checkable；共 107 项。


---

## 24. 表清单显示表注释（2026-11-03 追加）

表与视图清单增加「注释」列，取值来自 information_schema.TABLES.TABLE_COMMENT：

- TableInfo 增加可选字段 comment；MySQLDialect.list_tables 的统计查询改为同时取 TABLE_ROWS, TABLE_COMMENT（仍走 1.5 秒超时的尽力查询，超时则注释与行数一起为空，不阻塞列表）；视图的 TABLE_COMMENT='VIEW' 视为空。
- 表清单列：名称 / 类型 / 估算行数 / **注释** / 说明；注释列 Stretch 显示、超长截断并带 tooltip；说明（排除原因）改为固定宽度 + tooltip，避免长文本换行撑高行。
- 注释列可点击排序（与名称/类型/行数/说明一致）；表格 setWordWrap(False) 保持行高一致。
- 测试：方言注释解析（含视图注释过滤）与表清单注释显示/排序，共 108 项。


---

## 25. 行数自动精确统计（2026-11-03 追加）

**问题：** 列表里的「估算行数」来自 information_schema.TABLES.TABLE_ROWS，是 InnoDB 统计估算值（不随 DML 实时更新，视图固定 0），用户发现与实际不符。实测开发库：34 张里 10 张不一致、116 张里 18 张不一致，视图估算 0 / 实际 30,379。

**方案（自动，无需按钮）：**

- 列表先用 SHOW FULL TABLES 秒开，行数显示带 ~ 的估算值（tooltip 说明）。
- 当前库表清单渲染后，自动启动 RowCountWorker：逐表 SELECT COUNT(*)，每完成一张通过信号更新对应单元格为精确值（去掉 ~），工具栏显示「精确行数 N/M…」。
- 单表 COUNT 超过 10 秒（SET SESSION max_execution_time=10000）或失败：保留估算值并在 tooltip 标注原因，不阻塞后续表。
- 切换库 Tab / 开始导出 / 关闭窗口时取消统计：KILL QUERY 中断当前 COUNT，已完成的精确值保留在 _db_tables 缓存；TableInfo.rows_exact 标记是否已精确，重新进入 Tab 时只统计剩余表。
- 排序仍按当前值（估算或精确）进行；行数改为精确后不会自动重排，避免打断用户。
- 测试新增自动启动、逐表更新、精确/估算显示与取消逻辑，共 110 项。


---

## 26. 修复连接后不回显已保存库选择（2026-11-03 追加）

**现象：** 连接成功后左侧数据库列表全部未勾选，上次保存的库选择丢失。

**根因：** 点「连接」或「刷新」时都会调用 _collect_profile()，它把当前数据库列表的勾选状态写回 profile.selected_databases。但应用启动/切换配置时列表还是空的，于是连接前这一步把已保存的选择覆盖成了空数组；_on_databases_loaded 再读取时自然全不勾选。

**修复：**

- 新增 _database_loaded 标记：数据库列表尚未真正加载（_apply_profile 重置为 False，_on_databases_loaded 置 True）时，_collect_profile() 保留配置里已保存的 selected_databases，不用空列表覆盖。
- 列表加载后仍按原有逻辑用当前勾选状态回写；用户改选后再保存/刷新不会丢。
- 重建 Tab 时同步左侧列表的当前行到当前 Tab 对应的库，回显更直观。
- 回归测试覆盖「连接前 collect 不清空」「列表回显勾选」「改选后 collect 写入正确」，共 111 项。


---

## 27. 多库选择改用下拉切换（2026-11-03 追加）

用户勾选较多库时，右侧 Tab 栏被挤爆：标签截断、横向溢出、红框区域拥挤。改为按数量自适应：

- 勾选库 ≤ 6（TABS_MAX）：继续用 QFluentWidgets.TabBar，保持快速切换。
- 勾选库 > 6：隐藏 Tab，显示 ComboBox 下拉选择当前库（宽度 320，显示完整库名），下方表格与搜索/排除功能不变。
- 两种模式共用 _activate_database：下拉切换、Tab 点击、左侧点击都会同步当前库、左侧高亮行与表清单。
- 切换配置/重新加载数据库时两种控件都清空重建；导出期间下拉同样禁用。
- 测试：8 个库时断言 Tab 隐藏、下拉含 8 项、切换后当前库与左侧高亮同步（共 112 项）。


---

## 28. IDEA 风格可关闭 Tab（2026-11-03 追加，取代 §27 的下拉方案）

用户要求「像 IDEA 那样的 Tab，可以关闭，关闭左侧就不勾选了」。§27 的「库多改下拉」被本方案取代：

- 右侧始终使用 QFluentWidgets.TabBar：勾选几个库就有几个 Tab，库多时 Tab 栏**横向滚动**（setScrollable(True)，滚轮可横向滚），不再切换成下拉。
- **可关闭**：Tab 在悬停/当前时显示关闭按钮（TabCloseButtonDisplayMode.ON_HOVER）；点击关闭 = 左侧对应数据库取消勾选，Tab 随之重建；关闭当前 Tab 后自动切到剩余的第一个库。
- **+ 添加**：Tab 栏右侧保留「+」按钮，弹出未勾选数据库菜单，选择后左侧自动勾选并打开 Tab。
- 关闭回调用 QTimer.singleShot(0, ...) 延后取消勾选，避免在 TabBar 的点击信号内清空自身。
- 测试：8 个库时 Tab 仍可见可滚动、关闭 Tab 后左侧取消勾选且 Tab 数递减（共 113 项）。


---

## 29. 修复 Tab 滚轮滚动与左侧点击不同步（2026-11-03 追加）

**现象：** ① Tab 多了以后无法用鼠标滚轮横向滚动；② 点左侧数据库，表清单变了，但右侧 Tab 高亮没跟着切换。

**根因：**

- QFluentWidgets 的 TabBar 继承自 SingleDirectionScrollArea（QScrollArea），滚轮事件被其内部 viewport/smooth scroll 处理，垂直滚轮不会驱动横向滚动条；setScrollable(True) 只设置 Tab 最小宽度，不负责滚轮。
- _activate_database() 只更新 _current_db 和表清单，没有把 database_tabs 的 currentIndex 同步过去；只有 Tab 点击/重建时才设置索引。

**修复：**

- 新增 ScrollableTabBar(TabBar)：在 viewport 上安装事件过滤器，把 QEvent.Wheel 的 ngleDelta 映射到 horizontalScrollBar 的 value（横向滚动），事件被接受不再冒泡。
- _activate_database() 开头调用 _sync_tab_current(db)：按当前勾选库顺序找到索引并 setCurrentIndex（屏蔽信号），再调用 _ensure_tab_visible(index) 把标签滚进可视区域。
- _rebuild_database_tabs() 重建后同样确保当前 Tab 可见。
- 测试：滚轮事件能改变横向滚动条值、左侧点击同步 Tab 索引与文案（共 115 项）。


---

## 30. Tab 栏增加可见横向滚动条（2026-11-03 追加）

**现象：** Tab 多了以后虽然能用滚轮横向滚动，但没有任何可视滚动条，用户不知道还能往右滑。QFluentWidgets 的 TabBar 固定 ScrollBarAlwaysOff 且高度只有 46px，自带滚动条不可见。

**方案：** 在 Tab 栏下方加一条独立的 QScrollBar(Qt.Horizontal)（高 8px，细圆角样式），与 TabBar 内部隐藏的横向滚动条双向同步：

- inner.rangeChanged / inner.valueChanged → 更新外部滚动条的范围、页步长、可见性与位置；
- 外部 alueChanged → 写回 inner；
- inner.maximum() > 0 时才显示，否则隐藏（不占高度）；
- 重建 Tab 后用 QTimer.singleShot(0, ...) 同步一次，保证布局完成后的范围正确。

测试：多库时外部滚动条可见、最大值与内部一致，双向拖动数值同步（共 116 项）。


---

## 31. 移除 Tab 栏「+」按钮（2026-11-03 追加）

用户要求去掉 Tab 栏右侧的「+」添加按钮。处理：setAddButtonVisible(False)，删除 	abAddRequested 连接与 _on_tab_add_requested 菜单逻辑；新增库仍通过左侧数据库列表勾选（勾选后自动出现/恢复对应 Tab）。§28 中关于「+ 添加」的描述作废。


---

## 32. 配置输入框改为 Fluent 对话框（2026-11-03 追加）

新建/复制/重命名配置仍使用原生 QInputDialog（系统灰底、OK/Cancel 英文、默认字体），与主界面风格割裂。改为 InputDialog(FluentDialog)：

- 标题 + 说明 + LineEdit（带清空按钮、默认名预填）+ 校验提示；
- 名称空白时禁用「确定」，回车直接确认；
- 主/次按钮沿用 Fluent 样式（确定/取消）；
- 新建、复制、重命名三个入口统一走 _ask_text()；回归测试覆盖默认值与空名校验（共 117 项）。


---

## 33. 导出设置改为 Fluent 弹窗（2026-11-03 追加）

**现象：** 点「导出设置」展开内联选项面板后，底部栏变高，主区域被挤压，窗口高度不够时页面内容溢出/裁切（与之前日志内联展开的问题同源）。

**方案：** 去掉内联 options_panel，改为 OptionsDialog(FluentDialog) 弹窗：

- 弹窗包含「文件名带时间戳」「不输出 DROP」「中文转十六进制」与「每批行数」，点「保存」应用、「取消」放弃；
- 主窗口不再保存选项控件，改为 self._options: ExportOptions 状态；_apply_profile 从配置载入，_collect_profile 写回配置，导出时沿用同一对象；
- 页面布局高度固定，设置开关不再影响主区域；
- 测试：设置弹窗默认值/回写、按钮非 checkable、默认批量值（共 118 项）。


---

## 34. 去掉卡片模块的悬停上浮（2026-11-03 追加）

Card 继承 ElevatedCardWidget，该组件自带鼠标悬停时上浮 3px 的动画；卡片是页面骨架（连接/数据库/表与视图/底部栏），悬停晃动反而干扰阅读。处理：Card 覆写 nterEvent/leaveEvent，只 vent.accept()、不调用父类动画，卡片保持静止；按钮、Tab 的悬停反馈保留。测试：卡片进入悬停后动画保持 Stopped、位置不变（共 119 项）。


---

## 35. 底部导出栏也去掉悬停上浮（2026-11-03 追加）

§34 只处理了 Card，底部导出栏是直接 
ew ElevatedCardWidget()，悬停仍会上浮。新增 StaticCard(ElevatedCardWidget)（圆角阴影、覆写 enter/leave 不触发动画），Card 改为继承它，底部栏也改用 StaticCard；至此页面所有骨架卡片悬停都静止。测试：底部栏存在 StaticCard（共 120 项）。


---

## 36. 切换 Tab 后工作区布局稳定化（2026-11-03 追加）

**现象：** 用户反馈切换「表与视图」的库 Tab 后页面变形：右侧表卡片变为半宽、右侧留下大片空白，标题/搜索框被裁切、表格出现横向滚动。

**排查：** 在当前版本按以下方式均无法复现（切换后 splitter 始终满宽）：无头构造 + 直接激活库、真实连接 127.0.0.1 后点击 Tab、开启精确行数统计时切换、最大化/还原后切换、QT_SCALE_FACTOR=1.25。截图特征显示是**工作区 QSplitter/卡片的几何尺寸停留在旧的较小值**（右卡 459px，正常约 836px），不是表格数据或 Tab 控件内容问题；怀疑与窗口缩放/DPI 变化后布局未完全重排、而 Tab 切换触发了部分重绘有关。

**防御性修复：**

- 保存 self.workspace（QSplitter）与左右卡片引用，并给卡片设置最小宽度（260 / 520）。
- _stabilize_workspace()：先激活中央布局（处理 stale geometry），再检查 splitter 尺寸；若尺寸之和不等于可用宽度或右侧过窄，按 2:5 重新分配。
- 在 _activate_database（Tab 切换/左侧点库）与窗口 showEvent 后 QTimer.singleShot(0, ...) 调用一次稳定化。
- TableListWidget.set_tables 重建后把表格横/纵向滚动条复位到 0，避免切换库后停在旧滚动位置。
- 测试：splitter 旧尺寸被纠正、表格滚动位置复位（共 122 项）。

注意：由于无法本地复现，此修复是防御性的；若仍出现，需要用户提供复现步骤（是否最大化/双屏缩放/拖过分隔条后发生）。


---

## 37. 工作区改用固定布局，切 Tab 不再变形（2026-11-03 追加）

**现象：** §36 的防御性修复后仍每次切换 Tab 都变形：整个工作区向左缩、右侧留白、表格列被裁切，同时界面卡顿。

**根因判断：**

- QSplitter 保存的是绝对像素尺寸；切换 Tab 时表格/卡片内容重排、行数统计更新，分栏在部分布局周期里保留了旧的窄尺寸（截图里 workspace≈907 而非页面 1182），右侧留白、卡片被压缩后裁切。
- 切 Tab 会取消行数统计，RowCountWorker.cancel() 在 UI 线程里**新建一条 pymysql 连接执行 KILL QUERY**，网络慢时最多阻塞数秒，表现为「卡死」。

**修复：**

- 工作区从 QSplitter 改为普通 QHBoxLayout：左侧数据库卡片固定 340px，右侧表卡片 stretch=1 自适应；不再存在可拖拽/可残留的分栏像素尺寸。
- RowCountWorker.cancel() 改为纯标记取消，不再从 UI 线程连数据库；当前 COUNT 结束后线程自然退出（单条查询 10 秒超时封顶）。
- 切 Tab 实测 2–3ms，workspace 始终 (1202×597)，左右卡片 340/848 稳定。
- 测试：工作区无 QSplitter、右侧比左侧宽、铺满中央区域；共 122 项。


---

## 38. 页面卡片去掉阴影效果（重绘伪影根因排查，2026-11-03 追加）

§37 后用户仍反馈每次切 Tab 出现「模块左移/叠影/卡死」。所有布局几何日志（工作区、左右卡片宽度）始终正常，但截图呈现**旧画面与新画面叠加**，判断为 **Qt 重绘伪影**而非布局计算错误。

最可能的根因：卡片基类 ElevatedCardWidget 会给每个卡片挂 QGraphicsDropShadowEffect；相邻多个带图形效果的卡片在 Tab 切换、表格重排等高频重绘时，Windows 下容易出现 backing store 未完全失效导致的残影/错位。

**处理：** StaticCard 基类从 ElevatedCardWidget 改为 SimpleCardWidget（保留圆角与 1px 边框、无阴影、无悬停动画），页面所有卡片（连接/数据库/表与视图/底部栏）都不再携带 QGraphicsDropShadowEffect；配合 §37 的固定布局与非阻塞取消，切 Tab 不再触发残留绘制。

测试：卡片无 graphicsEffect、悬停位置不变；共 122 项。


---

## 39. 按用户要求恢复卡片悬停效果（2026-11-03 追加）

为帮助用户对比验证「切换 Tab 变形」是否由悬停/阴影效果引起，按用户要求把卡片基类从 SimpleCardWidget 恢复为 ElevatedCardWidget（恢复悬停上浮与阴影效果）；§37 的固定工作区布局、非阻塞取消行数统计保持不变。验证后再决定最终保留哪种卡片基类。

测试：卡片进入悬停后 levatedAni 处于 Running 状态（共 122 项）。


---

## 40. 按组件规范重构页面卡片（2026-11-03 追加）

**组件分工（QFluentWidgets）：** CardWidget 基础、SimpleCardWidget 静态面板（无阴影/无悬停）、ElevatedCardWidget 可悬停抬升的交互卡片、HeaderCardWidget 带标题卡片。

**此前用法问题：** 页面级大面板（连接/数据库/表与视图/底部栏）都用 ElevatedCardWidget，又用 nterEvent/leaveEvent 覆盖绕过它的悬停动画，阴影 QGraphicsDropShadowEffect 仍存在——属于「用交互卡片当静态面板 + 绕过组件状态机」，切 Tab 高频重绘时出现残影/错位。恢复悬停后组件走完整流程，问题消失，验证了这一判断。

**规范重构（最终形态）：**

- StaticCard 与页面 Card 都改继承 SimpleCardWidget：圆角 + 1px 边框、无阴影、无悬停动画，作为页面骨架；
- 删除自定义 nterEvent/leaveEvent 的悬停禁用 hack；
- 按钮、Tab、表格行保留各自组件的悬停反馈；
- 固定工作区布局（左 340 / 右自适应）与非阻塞取消行数统计保持不变；
- 测试：卡片为静态面板（无 graphicsEffect、无 elevatedAni、悬停不位移），6 库连续切换后卡片几何稳定（1202×597，340/848）；共 122 项。
