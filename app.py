import os
import sys

from dotenv import load_dotenv

from flask_jwt_auth_manager import JWTAuthManager
from flask_migrate import Migrate
from root import app, db

# Import all models, so that db.create_all() knows about their tables
from models.people import Person  # noqa: F401
import models.fantasy  # noqa: F401
from models.init_data import init_data


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


def _migration_filter(obj, name, type_, reflected, compare_to):
    """Alembic must never touch the read-only 'people' table (see models/people.py)."""
    if type_ == "table" and name == "people":
        return False
    return not (type_ in ("index", "unique_constraint") and getattr(getattr(obj, "table", None), "name", None) == "people")


migrate = Migrate(app, db, render_as_batch=True, include_object=_migration_filter)    # migrations live in ./migrations
JWTAuthManager(app)

# Importing the view modules registers their routes (@app.route) with the app
import views.index  # noqa: E402, F401
import views.api  # noqa: E402, F401  (FantaBall REST API, /api/...)

BASELINE_REVISION = "0001"


def init_database():
    """Bring the schema up to date with Alembic migrations (safe to run on every start).

    * Brand-new database: runs every migration.
    * Database created by the old db.create_all() (before migrations existed): stamped as the baseline, then upgraded.
    * db.create_all() afterwards only creates tables that are still missing (the read-only 'people' table).
    """
    from flask_migrate import stamp, upgrade
    from sqlalchemy import inspect

    tables = set(inspect(db.engine).get_table_names())
    if "alembic_version" not in tables and "leagues" in tables:
        stamp(revision=BASELINE_REVISION)
    upgrade()
    db.create_all()


from fantaball.cli import register as register_cli  # noqa: E402
register_cli(app)   # flask --app app nba <command>

# Create / migrate the schema, then (development only) add any missing initial rows.
# FLASK_SKIP_DB_INIT=true is for generating migrations (flask db migrate) against an empty database.
with app.app_context():
    if not app.config.get("SKIP_DB_INIT"):
        init_database()
        if app.config["ENVIRONMENT"] == "development":
            init_data()


if __name__ == "__main__":
    app.run()
