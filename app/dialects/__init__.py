"""数据库方言层：注册表与工厂。"""
from __future__ import annotations

from app.core.models import Profile

from .base import Dialect, DialectError, quote_ident
from .memory import MemoryDialect
from .mysql import MySQLDialect

DIALECTS: dict[str, type[Dialect]] = {
    MySQLDialect.name: MySQLDialect,
    MemoryDialect.name: MemoryDialect,
}

__all__ = ["DIALECTS", "Dialect", "DialectError", "create_dialect", "dialect_label",
           "quote_ident"]


def create_dialect(name: str, profile: Profile) -> Dialect:
    """按名字创建方言实例（构造时不连接）。"""
    cls = DIALECTS.get(name)
    if cls is None:
        raise DialectError("暂不支持的数据库类型：%s" % name)
    return cls(profile)


def dialect_label(name: str) -> str:
    cls = DIALECTS.get(name)
    return cls.label if cls is not None else name
