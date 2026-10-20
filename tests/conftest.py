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
os.environ["FLASK_CORS_ORIGINS"] = '["http://localhost:3000"]'


def make_jwt(email, name="Test User"):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'none'})}.{b64({'email': email, 'name': name})}.sig"


class Client:
    """Test client acting as one user. 'demo' = the built-in dummy user; others come in 'behind a proxy' with a JWT."""

    def __init__(self, flask_client, email=None):
        self.c = flask_client
        self.headers = {}
        if email:
            self.headers = {"X-Forwarded-For": "10.0.0.1", "Authorization": "Bearer " + make_jwt(email, email.split("@")[0])}

    def _req(self, method, url, data=None):
        kw = dict(headers=self.headers)
        if data is not None:
            kw["json"] = data
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
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture(scope="session")
def demo(flask_app):
    return Client(flask_app.test_client())


@pytest.fixture(scope="session")
def demo_league_id(demo):
    status, leagues = demo.get("/api/leagues")
    assert status == 200
    return next(l["id"] for l in leagues if l["is_demo"])


@pytest.fixture()
def alice(flask_app):
    return Client(flask_app.test_client(), "alice@example.com")


@pytest.fixture()
def bob(flask_app):
    return Client(flask_app.test_client(), "bob@example.com")
