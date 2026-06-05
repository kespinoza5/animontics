"""forge — build-time composition + staging of downstream-target artifacts.

forge takes a per-instance contract (config/mcus/<id>.yaml) plus a family of
reusable source modules (mcu/<family>/) and *composes* a buildable project on
the dev machine, compiles it to a flashable artifact (firmware/<id>/), and
(later) deploys it to the target over the host node's SSH access.

It is target-pluggable: MCU firmware is the first builder; FPGA bitstreams and
accelerator (Hailo/Coral) model compiles are future builders behind the same
Builder interface. See docs/forge.md.
"""
