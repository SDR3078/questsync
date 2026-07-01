"""Unit tests for the in-process credential store."""
from questsync import credstore


def test_put_get_overwrite_forget():
    credstore.put("user-a", "token-1")
    assert credstore.get("user-a") == "token-1"

    credstore.put("user-a", "token-2")            # overwrite
    assert credstore.get("user-a") == "token-2"

    assert credstore.get("unknown-user") is None  # miss

    credstore.forget("user-a")
    assert credstore.get("user-a") is None

    credstore.forget("user-a")                    # idempotent


def test_current_user():
    credstore.put("bob", "t")
    assert credstore.current_user() == "bob"      # used for the isolation assert
    credstore.forget("bob")
    assert credstore.current_user() is None
