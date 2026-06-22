from pathlib import Path

import openpyxl
from app.core.database import SessionLocal, init_db
from app.models.dataset import Dataset
from app.models.price_series import PriceSeries


def main():
    init_db()
    db = SessionLocal()
    path = Path(r"C:\Users\052000\Desktop\AnalysisAgent\yuebao\原油价格表. 20260603.xlsx")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb["2026年5月"]
    rows = list(ws.iter_rows(values_only=True))[:8]
    for i, r in enumerate(rows):
        print(i, r[:8])
    wb.close()

    count = db.query(PriceSeries).count()
    print("price count", count)
    ds = db.query(Dataset).all()
    print("datasets", [(d.id, d.name, d.category, d.row_count) for d in ds])
    db.close()


if __name__ == "__main__":
    main()
