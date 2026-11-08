import base64
import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Configure a throw-away database BEFORE importing the app (environment variables beat .env)
_tmp = tempfile.mkdtemp(prefix="fantaball-test-")
os.environ["FLASK_ENVIRONMENT"] = "development"
os.environ["FLASK_SITE_NAME"] = "FantaBall test"
os.environ["FLASK_SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ["FLASK_JWT_AUTH_DUMMY_USER_IF_NO_PROXY"] = "true"
os.environ["FLASK_JWT_AUTH_DEBUG"] = "false"
os.environ["FLASK_DEBUG"] = "false"
os.environ["FLASK_SYNC_INLINE"] = "true"        # admin sync runs synchronously in tests
os.environ["FLASK_ADMIN_EMAILS"] = '["admin@example.com"]'
os.environ["FLASK_CORS_ORIGINS"] = '["http://localhost:3000"]'
# Never let a developer's real .env (keys, season settings) leak into the tests: empty values count as "not set"
for _name in ("FLASK_NBA_SEASON_START", "FLASK_NBA_SEASON", "HIGHLIGHTLY_API_KEY", "BALLDONTLIE_API_KEY", "HIGHLIGHTLY_DAILY_QUOTA", "FLASK_NBA_PROVIDER"):
    os.environ[_name] = ""


def make_jwt(email, name="Test User"):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'none'})}.{b64({'email': email, 'name': name})}.sig"


class Client:
    """Test client acting as one user. No email = the local development login; others come in 'behind a proxy' with a JWT."""

    def __init__(self, flask_client, email=None):
        self.c = flask_client
        self.headers = {}
        if email:
            self.headers = {"X-Forwarded-For": "10.0.0.1", "Authorization": "Bearer " + make_jwt(email, email.split("@")[0])}

    def _req(self, method, url, data=None):
        kw = dict(headers=self.headers)
        if data is not None:
            kw["json"] = data
        # A fresh app context per request (like production): otherwise a context held open by the test body would
        # share flask.g - and with it the cached authenticated user - between requests of different users.
        with self.c.application.app_context():
            r = getattr(self.c, method)(url, **kw)
        return r.status_code, r.get_json(silent=True)

    def get(self, url):
        return self._req("get", url)

    def post(self, url, data=None):
        return self._req("post", url, data if data is not None else {})

    def put(self, url, data):
        return self._req("put", url, data)

    def patch(self, url, data):
        return self._req("patch", url, data)


@pytest.fixture(scope="session")
def flask_app():
    import app as app_module
    from fantaball import timeline
    from tests.helpers import TODAY  # noqa: F401
    from tests.mock_provider import MockNBAProvider
    app_module.app.config["TESTING"] = True
    # The application never ships a fake provider; tests install an offline fixture one.
    app_module.app.config["NBA_PROVIDER_FACTORY"] = lambda: MockNBAProvider(today=timeline.today())
    return app_module.app


@pytest.fixture()
def world(flask_app, monkeypatch):
    """An app context with EMPTY NBA tables, 'today' fixed to 2026-10-27."""
    from root import db
    from tests.helpers import TODAY, wipe_real_nba
    monkeypatch.setenv("FLASK_FAKE_TODAY", TODAY.isoformat())
    with flask_app.app_context():
        wipe_real_nba()
        yield
        db.session.rollback()
        wipe_real_nba()


@pytest.fixture()
def nba_data(world):
    """Same as `world`, with teams, players, schedule and box scores already imported (48 draftable players)."""
    from tests.helpers import TODAY, full_import
    from tests.mock_provider import MockNBAProvider
    full_import(MockNBAProvider(today=TODAY))


@pytest.fixture()
def local(flask_app):
    return Client(flask_app.test_client())


@pytest.fixture()
def alice(flask_app):
    return Client(flask_app.test_client(), "alice@example.com")


@pytest.fixture()
def bob(flask_app):
    return Client(flask_app.test_client(), "bob@example.com")


@pytest.fixture()
def admin(flask_app):
    return Client(flask_app.test_client(), "admin@example.com")
