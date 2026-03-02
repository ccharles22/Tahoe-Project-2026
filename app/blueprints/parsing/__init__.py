"""Parsing blueprint registration."""

from flask import Blueprint
parsing_bp = Blueprint("parsing", __name__, url_prefix="/parsing")

from . import routes  # noqa
