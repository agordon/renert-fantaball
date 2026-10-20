from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# The global Flask app and extension objects, so that every module
# (models, views) can do "from root import app, db" without circular imports.
# The actual initialization happens in 'app.py', after the configuration is loaded.
app = Flask(__name__)

db = SQLAlchemy()
