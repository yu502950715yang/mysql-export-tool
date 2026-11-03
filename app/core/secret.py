"""Windows DPAPI 加解密（仅当前用户作用域）。"""
from __future__ import annotations

import base64
import ctypes
import sys

IS_WINDOWS = sys.platform == "win32"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class SecretError(Exception):
    """密码加解密失败。"""


if IS_WINDOWS:
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _blob(data: bytes):
    """把 bytes 包成 DATA_BLOB，同时返回保持引用的 buffer。"""
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return buffer, blob


def _take_bytes(blob) -> bytes:
    """取走 DATA_BLOB 内容并释放系统分配的内存。"""
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def protect(plain: str) -> str:
    """加密明文密码，返回 base64 密文。"""
    if not IS_WINDOWS:
        raise SecretError("密码加密仅支持 Windows（DPAPI）")
    if plain == "":
        return ""
    raw = plain.encode("utf-8")
    buffer, blob_in = _blob(raw)
    blob_out = _DataBlob()
    ok = _crypt32.CryptProtectData(
        ctypes.byref(blob_in), "MysqlExportTool", None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise SecretError("DPAPI 加密失败，错误码 %s" % ctypes.get_last_error())
    encrypted = _take_bytes(blob_out)
    return base64.b64encode(encrypted).decode("ascii")


def unprotect(token: str) -> str:
    """解密 base64 密文，返回明文密码。"""
    if not IS_WINDOWS:
        raise SecretError("密码解密仅支持 Windows（DPAPI）")
    if token == "":
        return ""
    try:
        encrypted = base64.b64decode(token.encode("ascii"), validate=True)
    except Exception as exc:
        raise SecretError("密码密文格式无效") from exc
    if not encrypted:
        raise SecretError("密码密文格式无效")
    buffer, blob_in = _blob(encrypted)
    blob_out = _DataBlob()
    ok = _crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None,
                                     _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise SecretError("DPAPI 解密失败（配置可能来自其它 Windows 用户或机器）")
    return _take_bytes(blob_out).decode("utf-8", "replace")
