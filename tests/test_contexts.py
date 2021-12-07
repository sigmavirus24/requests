import attr
import pytest

from requests import auth
from requests import contexts


def test_default_session_context() -> None:
    try:
        contexts.SessionContext()
    except Exception as e:
        pytest.fail(f"unexpected exception {e}")


def test_default_request_context() -> None:
    try:
        contexts.RequestContext()
    except Exception as e:
        pytest.fail(f"unexpected exception {e}")


def test_session_context_with_validation() -> None:
    try:
        contexts.SessionContext(
            auth=auth.HTTPBasicAuth("username", "password"),
        )
    except Exception as e:
        pytest.fail(f"unexpected validation error {e}")


def test_create_request_context_from_session_context() -> None:
    sc = contexts.SessionContext(
        auth=auth.HTTPBasicAuth("username", "password"),
    )
    rc = sc.create_request_context(
        {
            "headers": {"X-Custom-Header": "Value"},
            "auth": auth.HTTPBasicAuth("otheruser", "differentpasswd"),
            "params": {"a": "b"},
        }
    )
    assert rc.auth == auth.HTTPBasicAuth("otheruser", "differentpasswd")
    assert rc.params == {"a": "b"}
    assert rc.headers["X-Custom-Header"] == "Value"


def test_create_request_context_from_session_context_merges_headers() -> None:
    sc = contexts.SessionContext(
        headers={
            "X-Custom-Header": "Default-Value",
            "X-Other-Header": "Unmodified",
        },
        auth=auth.HTTPBasicAuth("username", "password"),
    )
    rc = sc.create_request_context(
        {
            "headers": {"X-Custom-Header": "Specific-Value"},
            "auth": auth.HTTPBasicAuth("otheruser", "differentpasswd"),
            "params": {"a": "b"},
        }
    )
    assert rc.auth == auth.HTTPBasicAuth("otheruser", "differentpasswd")
    assert rc.params == {"a": "b"}
    assert rc.headers["X-Custom-Header"] == "Specific-Value"
    assert rc.headers["X-Other-Header"] == "Unmodified"


def test_request_context_is_immutable() -> None:
    rc = contexts.RequestContext()
    with pytest.raises(attr.exceptions.FrozenInstanceError):
        rc.allow_redirects = False
