"""Unit tests for the pluggable access policy."""
import pytest

from questsync import access


def test_default_is_allow_all():
    p = access.get_policy({})                       # unset -> allowall (the guarantee)
    assert p.check("any-random-uid") is True
    assert p.check("9fafd1a1-79e8-4c4e-a695-6b02d98b2806") is True


def test_allowlist_from_env():
    p = access.get_policy({"QUESTSYNC_ACCESS_POLICY": "allowlist",
                           "QUESTSYNC_ALLOWLIST": "a-1, b-2 , c-3"})
    assert p.check("a-1") is True and p.check("b-2") is True
    assert p.check("not-listed") is False


def test_allowlist_from_file_reloads(tmp_path):
    f = tmp_path / "allow.txt"
    f.write_text("# subscribers\nu-1\n  u-2  \n\n")
    p = access.get_policy({"QUESTSYNC_ACCESS_POLICY": "allowlist",
                           "QUESTSYNC_ALLOWLIST_FILE": str(f),
                           "QUESTSYNC_ALLOWLIST_TTL": "0"})   # TTL 0 -> always re-read
    assert p.check("u-1") is True and p.check("u-2") is True
    assert p.check("u-9") is False
    f.write_text("u-9\n")                                    # edit on the fly
    assert p.check("u-9") is True and p.check("u-1") is False


def test_http_requires_url():
    with pytest.raises(RuntimeError):
        access.get_policy({"QUESTSYNC_ACCESS_POLICY": "http"})


def test_unknown_policy_fails_closed():
    with pytest.raises(RuntimeError):
        access.get_policy({"QUESTSYNC_ACCESS_POLICY": "bogus"})
