"""验证 yuebao 样例导入和重复导入幂等性。

建议用临时数据库运行：
DATABASE_URL=sqlite:////tmp/analysisagent_verify.db python scripts/verify_sample_imports.py
"""
from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal, init_db
from app.services.data_import import DataImportService


ROOT = BACKEND_DIR.parent
SAMPLES = [
    (ROOT / "yuebao" / "原油价格表. 20260603.xlsx", "price"),
    (ROOT / "yuebao" / "供需平衡表.xlsx", "balance"),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        service = DataImportService(db)
        for path, category in SAMPLES:
            first = service.import_file(path, category)
            second = service.import_file(path, category)
            print(path.name)
            print("  first :", _brief(first))
            print("  second:", _brief(second))
            if first.get("inserted", 0) <= 0:
                raise SystemExit(f"{path.name} 首次导入未产生新增数据")
            if second.get("inserted", 0) != 0:
                raise SystemExit(f"{path.name} 重复导入产生了重复新增数据")
    finally:
        db.close()


def _brief(result: dict) -> dict:
    return {k: result.get(k) for k in ("rows", "inserted", "updated", "skipped")}


if __name__ == "__main__":
    main()
