"""Accounts 领域的单体路由适配器。"""
from app.core.dependencies import db
from app.modules.legacy_routes import select_routes
from account_service import main as legacy_accounts

# 过渡期端点继续复用成熟的 AccountService/Repository，实现上统一到单体连接池。
legacy_accounts.db = db
routes = select_routes(legacy_accounts.app, skip_paths={"/health"})
