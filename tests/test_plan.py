from app.core.models import ExcludeConfig, Profile
from app.core.plan import build_plan


def test_build_plan_reads_exclusions_from_profile():
    profile = Profile(name="dev",
                      databases={"db1": ExcludeConfig(["t1"], [".*_log$"])})
    plans = build_plan(profile, ["db1", "db2"])
    assert [item.db for item in plans] == ["db1", "db2"]
    assert plans[0].exclude.exclude_tables == ["t1"]
    assert plans[0].exclude.exclude_regexes == [".*_log$"]
    assert plans[1].exclude.exclude_tables == []


def test_build_plan_copies_exclusions():
    profile = Profile(name="dev", databases={"db1": ExcludeConfig(["t1"])})
    plan = build_plan(profile, ["db1"])[0]
    plan.exclude.exclude_tables.append("t2")
    assert profile.databases["db1"].exclude_tables == ["t1"]
