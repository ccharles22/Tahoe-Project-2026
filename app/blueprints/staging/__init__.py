from flask import Blueprint

staging_bp = Blueprint("staging", __name__, url_prefix="/staging")

from . import routes  # noqa: F401
