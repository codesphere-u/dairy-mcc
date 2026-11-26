"""CLI entrypoint for dairy-mcc."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from .mcc import MilkDelivery, evaluate_milk_intake, size_bulk_milk_chiller


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dairy-mcc",
        description="Test raw milk for water adulteration/SNF grading and size MCC bulk cooling tanks.",
    )
    parser.add_argument("--farmer", default="FARMER-001", help="Cooperative member ID.")
    parser.add_argument("--liters", type=Decimal, default=Decimal("45"), help="Delivered milk volume (L).")
    parser.add_argument("--lactometer", type=float, default=29.0, help="Observed Quevenne lactometer reading.")
    parser.add_argument("--temp-c", type=float, default=30.0, help="Measured milk temperature C.")
    parser.add_argument("--fat", type=float, default=4.0, help="Butterfat percent.")
    parser.add_argument("--resazurin", type=int, default=5, help="Resazurin disc reading (0..6).")
    parser.add_argument("--alcohol-clot", action="store_true", help="Alcohol test clotted (sour milk).")
    parser.add_argument("--mcc-daily-liters", type=float, default=2500.0, help="MCC total daily intake (L).")
    args = parser.parse_args(argv)

    receipt = evaluate_milk_intake(
        MilkDelivery(
            farmer_id=args.farmer,
            liters=args.liters,
            observed_lactometer=args.lactometer,
            milk_temp_c=args.temp_c,
            butterfat_pct=args.fat,
            resazurin_disc=args.resazurin,
            alcohol_test_clotted=args.alcohol_clot,
        )
    )
    chiller = size_bulk_milk_chiller(daily_intake_liters=args.mcc_daily_liters)
    print(
        json.dumps(
            {"intake_receipt": asdict(receipt), "chiller_sizing": asdict(chiller)},
            indent=2,
            default=_json_default,
        )
    )
    return 0 if receipt.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
