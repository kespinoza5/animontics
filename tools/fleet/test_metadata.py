"""Unit tests for the tier METADATA loader — one import-safe schema home per tier."""
from __future__ import annotations

import sys
import textwrap

from tools.fleet.reconcile import load_all_metadata, load_tier_metadata


def test_every_tier_loads_metadata():
    assert "tf_mini" in load_tier_metadata("sensors")
    devices = load_tier_metadata("devices")
    assert {"mcu_serial", "ads1115", "sara_r5", "si5351"} <= set(devices)
    effectors = load_tier_metadata("effectors")
    assert {"pwm", "fan_array", "servo", "power_rail", "speaker", "stream_sink"} <= set(effectors)
    policies = load_tier_metadata("policies")
    assert {"curve", "threshold"} <= set(policies)


def test_load_all_metadata_is_the_sensor_tier():
    assert load_all_metadata() == load_tier_metadata("sensors")


def test_metadata_descriptions_present():
    """`animon types` renders descriptions — every plugin must carry one."""
    for tier in ("devices", "effectors", "policies"):
        for t, meta in load_tier_metadata(tier).items():
            assert meta.get("description"), f"{tier}/{t} has no description"


def test_metadata_survives_class_import_failure(tmp_path, monkeypatch):
    """The point of the __init__.py home: a package whose class can't import
    (missing hardware dep) still contributes METADATA; a totally broken
    package is skipped without breaking the rest."""
    tier = "tier_test_metadata"
    root = tmp_path / tier
    (root / "guarded").mkdir(parents=True)
    (root / "broken").mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "guarded" / "__init__.py").write_text(textwrap.dedent("""
        try:
            import module_that_does_not_exist_anywhere
        except ImportError:
            pass
        METADATA = {"type": "guarded", "description": "still here"}
    """), encoding="utf-8")
    (root / "broken" / "__init__.py").write_text(
        "raise RuntimeError('package is hosed')\n", encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    loaded = load_tier_metadata(tier, tier_dir=root)
    assert loaded == {"guarded": {"type": "guarded", "description": "still here"}}
