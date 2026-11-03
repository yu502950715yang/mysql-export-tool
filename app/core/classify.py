"""表/视图分类：导出数据、仅结构、跳过。"""
from __future__ import annotations

import re

from .models import ClassifiedTable, ExcludeConfig, TableInfo


class RegexError(ValueError):
    """排除正则不合法。"""


def compile_regexes(regexes: list[str]) -> list[tuple[str, re.Pattern]]:
    """编译正则列表，空串忽略；非法正则抛 RegexError。"""
    compiled = []
    for pattern in regexes:
        text = (pattern or "").strip()
        if not text:
            continue
        try:
            compiled.append((text, re.compile(text, re.IGNORECASE)))
        except re.error as exc:
            raise RegexError("正则不合法：%s（%s）" % (text, exc)) from exc
    return compiled


def validate_regexes(regexes: list[str]) -> str | None:
    """校验正则，返回中文错误信息或 None。"""
    try:
        compile_regexes(regexes)
    except RegexError as exc:
        return str(exc)
    return None


def _match(name: str, compiled) -> str | None:
    for text, pattern in compiled:
        if pattern.match(name):
            return text
    return None


def classify_tables(tables: list[TableInfo], exclude: ExcludeConfig,
                    include_views: bool = True) -> list[ClassifiedTable]:
    """分类：表排除=仅结构，视图排除/关闭=不输出；正则优先于勾选。"""
    compiled = compile_regexes(exclude.exclude_regexes)
    unchecked = {name.lower() for name in exclude.exclude_tables if name}
    result = []
    for info in tables:
        hit = _match(info.name, compiled)
        is_unchecked = info.name.lower() in unchecked
        if info.is_view:
            if not include_views:
                result.append(ClassifiedTable(info, False, False, "已关闭视图导出"))
            elif hit:
                result.append(ClassifiedTable(info, False, False, "命中正则 %s" % hit))
            elif is_unchecked:
                result.append(ClassifiedTable(info, False, False, "未勾选"))
            else:
                result.append(ClassifiedTable(info, True, True, ""))
        else:
            if hit:
                result.append(ClassifiedTable(info, False, True, "命中正则 %s（仅结构）" % hit))
            elif is_unchecked:
                result.append(ClassifiedTable(info, False, True, "未勾选（仅结构）"))
            else:
                result.append(ClassifiedTable(info, True, True, ""))
    return result
