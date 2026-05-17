#!/usr/bin/env python3
"""
数据库初始化脚本
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import Base
from db.engine import engine


def init_database():
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("[OK] All tables created successfully.")

    # List created tables
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\nTables in database: {tables}")


if __name__ == "__main__":
    init_database()
