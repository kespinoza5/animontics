try:
    from sensors.servo_feedback.sensor import ServoFeedback
except ImportError:
    pass  # hardware deps not available on this platform

#: Proprioception — servo pot taps as joint angles. Device-fed array: channels
#: carry device+index (MCU uplink or SBC-side ADS1115), no direct connection.
METADATA = {
    "type": "servo_feedback",
    "name": "Servo position feedback (pot taps)",
    "description": "Joint proprioception from servo potentiometer wipers (divided "
                   "to the ADC rail), read via an MCU serial uplink or an SBC-side "
                   "ADS1115. counts→degrees calibration per channel.",
    "connection": {
        "supported": [],          # device-fed array; no direct connection
        "defaults": {},
        "valid": {},
    },
    "data_keys": {
        "seq": "int — most recent device frame sequence number",
        "raw": "dict[str,int] — raw ADC counts keyed by joint signal",
        "deg": "dict[str,float] — joint angle in degrees per servo_pot-calibrated "
               "channel (clamped to [deg_min, deg_max])",
    },
}

__all__ = ["ServoFeedback", "METADATA"]
