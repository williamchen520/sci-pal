"""System-domain blueprints, registered by ``api_server``.

Each module exposes ``build_*_blueprint(...)`` and receives its dependencies as
arguments, so routes can be tested without importing ``api_server`` (which pulls
in models and a database).
"""
