from flask import render_template

from flask_jwt_auth_manager import current_jwt_user, jwt_auth_required
from root import app


@app.route("/")
@jwt_auth_required
def index():
    """Home page."""
    return render_template("index.html", user=current_jwt_user)
