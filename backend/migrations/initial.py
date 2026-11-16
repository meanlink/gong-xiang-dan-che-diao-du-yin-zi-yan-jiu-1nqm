from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models  # noqa: F401  注册全部模型到 Base.metadata

# 既有表上的增量列（仅新增、不改类型），用于已存在数据卷的平滑升级；全新库由 create_all 建表
_ADDED_COLUMNS = {
    'datasets': {
        'origin': "VARCHAR(20) NOT NULL DEFAULT 'manual'",
        'recon_batch_id': 'INTEGER',
        'revision': 'INTEGER NOT NULL DEFAULT 1',
    },
}


def _ensure_columns():
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {col['name'] for col in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


def migrate():
    Base.metadata.create_all(engine)
    _ensure_columns()


if __name__ == '__main__':
    migrate()
