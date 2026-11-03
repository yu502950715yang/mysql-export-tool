from app.main import main


def test_main_routes_cli(capsys):
    assert main(["--version"]) == 0
    assert "MysqlExportTool" in capsys.readouterr().out
