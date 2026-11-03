import pymysql

from app.core.errors import AppError, translate_exception


def test_auth_error_translated():
    err = translate_exception(pymysql.err.OperationalError(1045, "Access denied for user"))
    assert isinstance(err, AppError)
    assert "用户名或密码" in err.message
    assert "Access denied" in err.detail


def test_network_error_translated():
    err = translate_exception(pymysql.err.OperationalError(2003, "Can't connect"))
    assert "无法连接" in err.message


def test_unknown_error_keeps_detail():
    err = translate_exception(RuntimeError("boom"))
    assert err.message == "数据库操作失败"
    assert "boom" in err.detail


def test_app_error_passthrough():
    original = AppError("自定义错误", detail="d")
    assert translate_exception(original) is original


def test_os_error_translated():
    err = translate_exception(PermissionError("denied"))
    assert err.message == "文件写入失败"
