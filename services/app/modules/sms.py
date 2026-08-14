"""SMS 领域的单体路由适配器。"""
from app.core.dependencies import db
from app.modules.legacy_routes import select_routes
from sms_service import main as legacy_sms

# 保留 provider registry 的导入副作用与所有第三方 provider 实现，仅替换进程边界。
legacy_sms.db = db
routes = select_routes(legacy_sms.app, skip_paths={"/health"})
