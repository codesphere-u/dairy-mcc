"""Tests for dairy-mcc."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from dairy_mcc import (
    MilkDelivery,
    MilkGrade,
    corrected_lactometer_reading,
    evaluate_milk_intake,
    richmond_snf_pct,
    size_bulk_milk_chiller,
)
from dairy_mcc.cli import main as cli_main


def test_lactometer_temp_correction_and_richmond_snf() -> None:
    # Fresh warm milk at 30C reading 28.0 corrects to 30.0 at 20C
    clr = corrected_lactometer_reading(28.0, milk_temp_c=30.0)
    assert clr == pytest.approx(30.0)
    snf = richmond_snf_pct(clr, butterfat_pct=4.0)
    assert snf == pytest.approx(8.70, abs=0.02)


def test_premium_acceptance_vs_water_adulteration_and_skimming_reject() -> None:
    premium = evaluate_milk_intake(
        MilkDelivery("F1", Decimal("50"), observed_lactometer=28.5, milk_temp_c=30.0, butterfat_pct=4.1)
    )
    assert premium.accepted is True
    assert premium.grade == MilkGrade.GRADE_A_PREMIUM
    assert premium.gross_payout == Decimal("19.50")

    watered = evaluate_milk_intake(
        MilkDelivery("F2", Decimal("50"), observed_lactometer=21.0, milk_temp_c=25.0, butterfat_pct=3.0)
    )
    assert watered.accepted is False
    assert watered.estimated_added_water_pct > 15.0
    assert watered.gross_payout == Decimal("0.00")

    skimmed = evaluate_milk_intake(
        MilkDelivery("F3", Decimal("30"), observed_lactometer=34.0, milk_temp_c=25.0, butterfat_pct=2.2)
    )
    assert skimmed.accepted is False
    assert skimmed.suspected_skimming is True


def test_bulk_chiller_sizing_and_cli(capsys: pytest.CaptureFixture[str]) -> None:
    ch = size_bulk_milk_chiller(daily_intake_liters=2000.0)
    assert ch.recommended_tank_liters == 3000
    assert ch.compressor_electrical_kw > 8.0
    assert ch.solar_pv_kwp_direct_icebank > 9.0

    assert cli_main(["--liters", "40", "--lactometer", "29", "--temp-c", "30", "--fat", "4.0"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["intake_receipt"]["grade"] == "grade_a_premium"
