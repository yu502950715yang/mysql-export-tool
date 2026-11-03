"""异常分类与用户可读中文消息。"""
from __future__ import annotations


class AppError(Exception):
    """用户可读错误：message 给界面，detail 给日志。"""

    def __init__(self, message: str, detail: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.hint = hint


_DB_ERROR_MAP = {
    1045: ("用户名或密码错误", "检查用户名、密码以及账号是否允许从当前主机登录"),
    1044: ("数据库访问被拒绝", "账号缺少该库权限"),
    1049: ("数据库不存在", "刷新库列表后重新选择"),
    1142: ("权限不足", "账号缺少该表或视图的 SELECT 权限"),
    2003: ("无法连接目标主机/端口", "检查网络、防火墙与端口号"),
    2013: ("连接已断开", "网络不稳定或服务器超时，请重试"),
}


def translate_db_error(exc: BaseException) -> AppError:
    """把 PyMySQL 常见错误码翻译成中文提示。"""
    errno = None
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], int):
        errno = args[0]
    if errno in _DB_ERROR_MAP:
        message, hint = _DB_ERROR_MAP[errno]
        return AppError(message, detail=str(exc), hint=hint)
    return AppError("数据库操作失败", detail=str(exc), hint="查看日志获取完整堆栈")


def translate_exception(exc: BaseException) -> AppError:
    """统一异常入口：AppError 原样返回，OSError 归为文件写入问题。"""
    if isinstance(exc, AppError):
        return exc
    if isinstance(exc, OSError):
        return AppError("文件写入失败", detail=str(exc),
                        hint="检查输出目录是否存在、是否有写入权限、磁盘空间是否充足")
    return translate_db_error(exc)
