"""Dairy MCC lactometer adulteration, Richmond SNF formula, chiller sizing & cooperative payouts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

_Q2 = Decimal("0.01")


class MilkGrade(StrEnum):
    GRADE_A_PREMIUM = "grade_a_premium"
    GRADE_B_STANDARD = "grade_b_standard"
    REJECTED = "rejected"


def corrected_lactometer_reading(
    observed_clr: float,
    milk_temp_c: float,
    *,
    calibration_temp_c: float = 20.0,
) -> float:
    """Correct Quevenne lactometer reading to calibration temp (20C): +/-0.2 deg per 1C."""
    if not (5.0 <= milk_temp_c <= 42.0):
        raise ValueError(f"milk_temp_c out of range [5, 42] C: {milk_temp_c}")
    return observed_clr + 0.2 * (milk_temp_c - calibration_temp_c)


def richmond_snf_pct(clr_20c: float, butterfat_pct: float) -> float:
    """Richmond's formula for Solids-Not-Fat (%): SNF = CLR/4 + 0.21*Fat + 0.36."""
    return (clr_20c / 4.0) + (0.21 * butterfat_pct) + 0.36


@dataclass(frozen=True)
class MilkDelivery:
    """Single smallholder raw-milk delivery tested at the MCC platform."""

    farmer_id: str
    liters: Decimal
    observed_lactometer: float  # Quevenne degrees (normal cow milk 28..33)
    milk_temp_c: float
    butterfat_pct: float = 3.8
    alcohol_test_clotted: bool = False  # 68%-72% ethanol clot => high acidity / souring
    resazurin_disc: int = 5  # Lovibond 6 (blue, excellent) down to 0 (white, spoiled)
    antibiotic_residue_positive: bool = False

    def __post_init__(self) -> None:
        if self.liters <= 0:
            raise ValueError("liters must be positive")
        if not (0.0 <= self.butterfat_pct <= 12.0):
            raise ValueError("butterfat_pct out of range [0, 12]")
        if not (0 <= self.resazurin_disc <= 6):
            raise ValueError("resazurin_disc must be in [0, 6]")


@dataclass(frozen=True)
class MilkIntakeReceipt:
    """Platform acceptance decision, adulteration diagnostics, and exact Decimal farmer payout."""

    farmer_id: str
    liters_delivered: Decimal
    corrected_lactometer_20c: float
    specific_gravity: float
    snf_pct: float
    estimated_added_water_pct: float
    suspected_skimming: bool
    grade: MilkGrade
    accepted: bool
    unit_price_per_liter: Decimal
    gross_payout: Decimal
    rejection_reasons: tuple[str, ...]


def evaluate_milk_intake(
    delivery: MilkDelivery,
    *,
    base_price_per_liter: Decimal = Decimal("0.35"),
    grade_a_bonus_per_liter: Decimal = Decimal("0.04"),
    min_snf_pct: float = 8.5,
    min_butterfat_pct: float = 3.25,
) -> MilkIntakeReceipt:
    """Run EAC/EAS 67 raw-milk platform quality tests, detect water adulteration & compute payout."""
    clr = corrected_lactometer_reading(delivery.observed_lactometer, delivery.milk_temp_c)
    sg = 1.0 + (clr / 1000.0)
    snf = richmond_snf_pct(clr, delivery.butterfat_pct)

    # Estimate water dilution when CLR falls below East African raw cow-milk floor (28.0 deg)
    added_water = max(0.0, ((28.0 - clr) / 28.0) * 100.0) if clr < 28.0 else 0.0
    # High density (>33 deg) paired with low butterfat (<3.0%) indicates cream skimming
    skimmed = clr > 33.0 and delivery.butterfat_pct < 3.0

    reasons: list[str] = []
    if delivery.antibiotic_residue_positive:
        reasons.append("ANTIBIOTIC RESIDUE POSITIVE: discard lot to protect fermented/yoghurt cultures & consumers.")
    if delivery.alcohol_test_clotted:
        reasons.append(
            "ALCOHOL TEST CLOT: developed lactic acidity / incipient souring; will curdle on pasteurization."
        )
    if delivery.resazurin_disc <= 2:
        reasons.append(f"POOR MICROBIAL QUALITY (Resazurin disc {delivery.resazurin_disc} <= 2): high bacterial load.")
    if clr < 26.5:
        reasons.append(
            f"WATER ADULTERATION REJECT: corrected lactometer {clr:.1f} (<26.5; ~{added_water:.1f}% added water)."
        )
    if snf < min_snf_pct - 0.5:
        reasons.append(f"LOW SNF REJECT: {snf:.2f}% below EAS 67 minimum floor.")
    if skimmed:
        reasons.append(f"SUSPECTED SKIMMING: elevated CLR {clr:.1f} with butterfat {delivery.butterfat_pct:.2f}%.")

    if reasons:
        grade = MilkGrade.REJECTED
        unit_price = Decimal("0.00")
        payout = Decimal("0.00")
    elif (
        delivery.resazurin_disc >= 5
        and delivery.butterfat_pct >= 3.8
        and snf >= min_snf_pct
        and 28.0 <= clr <= 33.0
    ):
        grade = MilkGrade.GRADE_A_PREMIUM
        unit_price = (base_price_per_liter + grade_a_bonus_per_liter).quantize(_Q2, rounding=ROUND_HALF_UP)
        payout = (delivery.liters * unit_price).quantize(_Q2, rounding=ROUND_HALF_UP)
    else:
        grade = MilkGrade.GRADE_B_STANDARD
        unit_price = base_price_per_liter.quantize(_Q2, rounding=ROUND_HALF_UP)
        payout = (delivery.liters * unit_price).quantize(_Q2, rounding=ROUND_HALF_UP)

    return MilkIntakeReceipt(
        farmer_id=delivery.farmer_id,
        liters_delivered=delivery.liters.quantize(_Q2, rounding=ROUND_HALF_UP),
        corrected_lactometer_20c=round(clr, 2),
        specific_gravity=round(sg, 4),
        snf_pct=round(snf, 2),
        estimated_added_water_pct=round(added_water, 1),
        suspected_skimming=skimmed,
        grade=grade,
        accepted=grade != MilkGrade.REJECTED,
        unit_price_per_liter=unit_price,
        gross_payout=payout,
        rejection_reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class ChillerSizingResult:
    """ISO 5708 3-hour pulldown bulk milk cooling-tank thermal & solar/generator sizing."""

    daily_intake_liters: float
    recommended_tank_liters: int
    pulldown_thermal_kwh: float
    compressor_thermal_kw_3h: float
    compressor_electrical_kw: float
    daily_electrical_kwh: float
    solar_pv_kwp_direct_icebank: float


def size_bulk_milk_chiller(
    *,
    daily_intake_liters: float,
    intake_temp_c: float = 32.0,
    target_temp_c: float = 4.0,
    pulldown_hours: float = 3.0,  # ISO 5708 standard: cool milking batch to 4C within 3 hours
    cop: float = 2.4,
    peak_sun_hours: float = 5.0,
) -> ChillerSizingResult:
    """Size MCC bulk milk cooling tank, refrigeration compressor kW, and solar ice-bank PV kWp."""
    if daily_intake_liters <= 0 or intake_temp_c <= target_temp_c or pulldown_hours <= 0:
        raise ValueError("Invalid milk intake volume, temperatures, or pulldown hours")

    # Standard MCC bulk tank sizes (L) with 25% flush-season surge buffer
    req_tank = daily_intake_liters * 1.25
    std_tanks = (500, 1000, 1500, 2000, 3000, 5000, 8000, 10000)
    tank_l = next((t for t in std_tanks if t >= req_tank), int((req_tank // 2000 + 1) * 2000))

    # Milk density ~1.03 kg/L, specific heat ~3.93 kJ/(kg*K) + 15% tank/agitator heat gain
    mass_kg = daily_intake_liters * 1.03
    q_pulldown_kwh = (mass_kg * 3.93 * (intake_temp_c - target_temp_c) / 3600.0) * 1.15
    comp_th_kw = q_pulldown_kwh / pulldown_hours
    comp_el_kw = comp_th_kw / cop
    daily_el_kwh = (q_pulldown_kwh / cop) * 1.20  # +20% 24h holding + CIP wash losses
    pv_kwp = (daily_el_kwh * 1.15) / (peak_sun_hours * 0.75)

    return ChillerSizingResult(
        daily_intake_liters=round(daily_intake_liters, 1),
        recommended_tank_liters=tank_l,
        pulldown_thermal_kwh=round(q_pulldown_kwh, 2),
        compressor_thermal_kw_3h=round(comp_th_kw, 2),
        compressor_electrical_kw=round(comp_el_kw, 2),
        daily_electrical_kwh=round(daily_el_kwh, 2),
        solar_pv_kwp_direct_icebank=round(pv_kwp, 2),
    )
