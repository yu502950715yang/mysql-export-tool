"""由 profile 与勾选库生成导出计划。"""
from __future__ import annotations

from .models import DatabasePlan, ExcludeConfig, Profile


def build_plan(profile: Profile, databases: list[str]) -> list[DatabasePlan]:
    """生成计划；排除配置做深拷贝，后续界面修改不影响 profile。"""
    plans = []
    for db in databases:
        exclude = profile.exclude_for(db)
        plans.append(DatabasePlan(db=db, exclude=ExcludeConfig(
            exclude_tables=list(exclude.exclude_tables),
            exclude_regexes=list(exclude.exclude_regexes))))
    return plans
