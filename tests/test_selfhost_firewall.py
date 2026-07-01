"""Guards that keep the self-host path clean (the panel's 'dependency firewall'):
the facade image must never gain a billing SDK or a database driver, and the
default access policy must be allow-all — so self-host can never accidentally be
made to require billing/entitlement config."""
from pathlib import Path

import pytest

from questsync import access

# Billing SDKs and DB/cache drivers that must never enter the stateless facade image.
_FORBIDDEN = ["stripe", "psycopg", "asyncpg", "sqlalchemy", "mysqlclient",
              "pymysql", "redis", "boto3", "pymongo", "mongoengine"]


def test_facade_image_has_no_billing_or_db_deps():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    if not dockerfile.exists():
        pytest.skip("Dockerfile not present in this test context")
    text = dockerfile.read_text().lower()
    hits = [name for name in _FORBIDDEN if name in text]
    assert not hits, "facade image must stay billing/DB-free; found: %s" % hits


def test_vanilla_config_allows_everyone():
    # No access config at all -> anyone with valid Habitica creds gets in.
    assert access.get_policy({}).check("some-user") is True
