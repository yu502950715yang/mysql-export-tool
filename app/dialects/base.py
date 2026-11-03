"""数据库方言抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from app.core.errors import AppError
from app.core.literal import quote_ident
from app.core.models import ExportOptions, Profile, TableInfo

__all__ = ["Dialect", "DialectError", "quote_ident"]


class DialectError(AppError):
    """方言层错误（用户可直接读）。"""


class Dialect(ABC):
    """一种数据库的适配层：元数据发现、DDL、数据流式读取、字面量编码。"""

    name: str = ""
    label: str = ""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def ping(self) -> str: ...

    @abstractmethod
    def list_databases(self, include_system: bool = False) -> list[str]: ...

    @abstractmethod
    def list_tables(self, db: str) -> list[TableInfo]: ...

    @abstractmethod
    def create_table_sql(self, db: str, table: str) -> str: ...

    @abstractmethod
    def drop_table_sql(self, table: str) -> str: ...

    @abstractmethod
    def create_view_sql(self, db: str, view: str) -> str: ...

    @abstractmethod
    def drop_view_sql(self, view: str) -> str: ...

    @abstractmethod
    def stream_rows(self, db: str, table: str,
                    batch: int) -> Iterator[tuple[list[str], list[tuple]]]: ...

    @abstractmethod
    def literal(self, value, options: ExportOptions) -> str: ...
