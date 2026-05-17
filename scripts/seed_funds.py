#!/usr/bin/env python3
"""
导入基金清单
"""
import sys
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.engine import get_session
from db.models import Fund


def seed_funds(csv_path: str = None):
    if csv_path is None:
        csv_path = Path(__file__).parent.parent / "config" / "fund_list.csv"

    print(f"Reading fund list from {csv_path}...")

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        funds = list(reader)

    print(f"Found {len(funds)} funds in CSV.")

    with get_session() as session:
        existing_ciks = {f.cik for f in session.query(Fund.cik).all()}
        added = 0
        skipped = 0
        seen_ciks = set()

        for row in funds:
            cik = row["cik"].strip()
            if cik in existing_ciks or cik in seen_ciks:
                skipped += 1
                continue

            seen_ciks.add(cik)
            fund = Fund(
                cik=cik,
                name=row["name"].strip(),
                manager=row.get("manager", "").strip() or None,
                strategy=row.get("strategy", "").strip() or None,
                is_active=True,
            )
            session.add(fund)
            added += 1

        print(f"Added: {added}, Skipped (already exists or duplicate): {skipped}")
        print("[OK] Fund seeding complete.")


if __name__ == "__main__":
    seed_funds()
