"""Configuration 领域的单体路由适配器。"""
from app.core.dependencies import db
from app.modules.legacy_routes import select_routes
from config_service import main as legacy_configuration

legacy_configuration.db = db
routes = select_routes(legacy_configuration.app, skip_paths={"/health"})
