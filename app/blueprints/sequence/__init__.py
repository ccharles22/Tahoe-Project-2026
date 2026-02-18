from flask import Blueprint

sequence_bp = Blueprint("sequence", __name__, url_prefix="/api")

from . import routes  # noqa: F401
