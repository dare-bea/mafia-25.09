"""A Web API for mafia games. Includes a blueprint for the API and a database of games.

The API is versioned, and each version has its own blueprint,
but they are all registered under the same URL prefix (`/api`).
The most recent version is `v1`.
"""

__all__ = [
    "api_bp",
    "core",
    "v0",
    "v1",
]

from flask import Blueprint

from . import core, v0, v1

# Create API blueprint as a collection of all API versions.
api_bp = Blueprint("api", __name__)
api_bp.register_blueprint(v0.api_bp)
api_bp.register_blueprint(v1.api_bp)
