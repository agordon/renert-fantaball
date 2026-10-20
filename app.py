import os
import sys

from dotenv import load_dotenv

from flask_jwt_auth_manager import JWTAuthManager
from root import app, db

# Import all models, so that db.create_all() knows about their tables
from models.people import Person  # noqa: F401
import models.fantasy  # noqa: F401
from models.init_data import init_data
from fantaball.seed import load_world, seed_demo_league
from fantaball.providers import DemoProvider


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# These must be set in the .env file (as FLASK_XXX), the app will not start without them
REQUIRED_CONFIG_KEYS = [
    "ENVIRONMENT",
    "SITE_NAME",
    "SQLALCHEMY_DATABASE_URI",
]

ENVIRONMENTS = ["development", "production"]


# Every "FLASK_XXX" variable (from .env or the environment) becomes app.config["XXX"]
load_dotenv(os.path.join(BASE_DIR, ".env"))
app.config.from_prefixed_env()

missing_keys = [key for key in REQUIRED_CONFIG_KEYS if key not in app.config]
if missing_keys:
    missing_names = ", ".join(f"FLASK_{key}" for key in missing_keys)
    sys.exit(f"Error: missing required configuration in .env: {missing_names}")

if app.config["ENVIRONMENT"] not in ENVIRONMENTS:
    sys.exit(f"Error: FLASK_ENVIRONMENT must be one of: {', '.join(ENVIRONMENTS)}")

os.makedirs(app.instance_path, exist_ok=True)

db.init_app(app)
JWTAuthManager(app)

# Importing the view modules registers their routes (@app.route) with the app
import views.index  # noqa: E402, F401
import views.api  # noqa: E402, F401  (FantaBall REST API, /api/...)

# Create any missing tables (existing tables are not modified), then (development only) add any missing initial rows
with app.app_context():
    db.create_all()
    if app.config["ENVIRONMENT"] == "development":
        init_data()
    # FantaBall: the simulated sports world is needed in every environment (idempotent);
    # the pre-played demo league is development-only, like init_data().
    for _sport in ("nba", "nhl"):
        load_world(DemoProvider(_sport))
    if app.config["ENVIRONMENT"] == "development":
        seed_demo_league(
            app.config.get("JWT_AUTH_DUMMY_USER_EMAIL", "john.doe@example.com"),
            f"{app.config.get('JWT_AUTH_DUMMY_USER_FIRST_NAME', 'John')} {app.config.get('JWT_AUTH_DUMMY_USER_LAST_NAME', 'Doe')}",
        )


if __name__ == "__main__":
    app.run()
