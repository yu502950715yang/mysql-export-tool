from app.selftest import run_selftest


def test_selftest_passes():
    ok, lines = run_selftest()
    assert ok, "\n".join(lines)
    assert lines[-1] == "SELFTEST OK"
    assert any("排除表无数据" in line for line in lines)
    assert any("排除表保留建表" in line for line in lines)
