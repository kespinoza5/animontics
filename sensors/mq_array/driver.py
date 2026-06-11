"""MQ gas-sensor math — pure functions, no I/O, no hardware.

MQ-series sensors are resistive: a heated element's resistance Rs falls as target
gas rises. The board reads the voltage across a load resistor RL, which the MCU
digitizes to a raw ADC count. Datasheet ppm curves are all plotted against the
ratio Rs/R0, where R0 is the sensor's resistance in clean air (per-unit, measured
during calibration). These helpers convert raw counts → that ratio; turning the
ratio into ppm needs per-gas curve constants and is deferred.
"""
from __future__ import annotations

ADC_MAX = 1023   # ATmega328P 10-bit ADC full scale


def rs_over_rl(raw: int, adc_max: int = ADC_MAX) -> float | None:
    """Rs/RL from a raw ADC count: (adc_max - raw) / raw.

    Returns None for raw <= 0 (open input / no reading) to avoid divide-by-zero.
    """
    if raw <= 0:
        return None
    return (adc_max - raw) / raw


def rs_over_r0(raw: int, rl_ohms: float, r0_ohms: float,
               adc_max: int = ADC_MAX) -> float | None:
    """Rs/R0 ratio — the x-axis of every MQ datasheet ppm curve.

    Needs the load resistor RL and the clean-air baseline R0 (both ohms).
    Returns None when the inputs are unusable (raw <= 0 or r0 <= 0).
    """
    ratio = rs_over_rl(raw, adc_max)
    if ratio is None or r0_ohms <= 0:
        return None
    return ratio * rl_ohms / r0_ohms
