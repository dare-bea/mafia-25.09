__all__ = [
    "v0",
    "v1",
    "core"
]

from flask import Blueprint

from . import v0
from . import v1
from . import core

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(v0.api_bp)
api_bp.register_blueprint(v1.api_bp)