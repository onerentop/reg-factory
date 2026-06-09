import os

os.environ["DB_SCHEMA_PREFIX"] = "none"


def create_tables_without_schema(sync_conn):
    """SQLite 不支持 schema，只创建无 schema 的表。"""
    from shared.base_model import BaseModel
    tables = [t for t in BaseModel.metadata.tables.values() if t.schema is None]
    BaseModel.metadata.create_all(sync_conn, tables=tables)
