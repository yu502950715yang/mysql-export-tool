"""SQL 值字面量编码（策略与旧脚本一致）。"""
from __future__ import annotations


def clean_value(value):
    """清洗字符串：非法 UTF-8/代理字符替换为 ?，保证文件可写、可导入。"""
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8")
    return value


def sql_literal(conn, value, escape_unicode=True):
    """把 Python 值编码为 SQL 字面量。

    非 ASCII 字符串转 utf8mb4 十六进制，保证导出文件纯 ASCII 且不乱码；
    空 blob 必须用 _binary ''（MySQL 8 下 `_binary 0x` 是语法错误）。
    """
    if value is None:
        return "NULL"
    if isinstance(value, (bytes, bytearray)):
        data = bytes(value)
        if not data:
            return "_binary ''"
        return "_binary 0x%s" % data.hex()
    if isinstance(value, str):
        cleaned = clean_value(value)
        if cleaned.isascii() or not escape_unicode:
            return conn.escape(cleaned)
        return "_utf8mb4 0x%s" % cleaned.encode("utf-8").hex()
    return conn.escape(clean_value(value))


def quote_ident(name: str) -> str:
    """用反引号包裹标识符（MySQL 规则），转义内部反引号。"""
    return "`%s`" % str(name).replace("`", "``")
