import pytest

from app.core.literal import clean_value, quote_ident, sql_literal


class FakeConn:
    """模拟 PyMySQL 连接的 escape 行为。"""

    def escape(self, value):
        if isinstance(value, str):
            escaped = (value.replace("\\", "\\\\").replace("'", "\\'")
                       .replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r"))
            return "'%s'" % escaped
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)


@pytest.fixture()
def conn():
    return FakeConn()


def test_none_literal(conn):
    assert sql_literal(conn, None) == "NULL"


def test_empty_bytes_uses_empty_binary_literal(conn):
    assert sql_literal(conn, b"") == "_binary ''"


def test_nonempty_bytes_is_hex(conn):
    assert sql_literal(conn, b"\x00\xff") == "_binary 0x00ff"


def test_ascii_string_escaped(conn):
    assert sql_literal(conn, "O'Brien") == "'O\\'Brien'"


def test_non_ascii_uses_utf8mb4_hex(conn):
    assert sql_literal(conn, "张三") == "_utf8mb4 0x" + "张三".encode("utf-8").hex()


def test_non_ascii_without_escape_uses_plain_string(conn):
    assert sql_literal(conn, "张三", escape_unicode=False) == "'张三'"


def test_surrogate_is_cleaned(conn):
    assert sql_literal(conn, "a\ud800b") == "'a?b'"


def test_number_is_plain(conn):
    assert sql_literal(conn, 42) == "42"
    assert sql_literal(conn, 1.5) == "1.5"


def test_clean_value_leaves_non_string_untouched():
    assert clean_value(3) == 3


def test_quote_ident_escapes_backtick():
    assert quote_ident("users") == "`users`"
    assert quote_ident("we`ird") == "`we``ird`"
