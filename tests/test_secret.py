import sys

import pytest

from app.core import secret

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI 仅 Windows")


def test_protect_unprotect_roundtrip():
    token = secret.protect("demo-password")
    assert token and token != "demo-password"
    assert secret.unprotect(token) == "demo-password"


def test_empty_password_roundtrip():
    assert secret.protect("") == ""
    assert secret.unprotect("") == ""


def test_invalid_token_raises_secret_error():
    with pytest.raises(secret.SecretError):
        secret.unprotect("not-a-valid-token")
