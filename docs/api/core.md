# core — API Reference

The `core` package is the **cortex runtime** plus shared infrastructure. No
hardware dependencies — importable on any machine (hardware libs load lazily).

## sensor_base

::: core.sensor_base.SensorBase

## analog_array

::: core.analog_array.AnalogArrayBase

## device

The base class, registry, and factory for devices. Concrete kinds
(`McuSerialDevice`, `Ads1115Device`, `SaraR5Device`) live in the `devices/`
plugin tree, auto-discovered like sensors.

::: core.device.Device
::: core.device.create_device

### devices.mcu_serial

::: devices.mcu_serial.device.McuSerialDevice

### devices.ads1115

::: devices.ads1115.device.Ads1115Device

### devices.sara_r5

::: devices.sara_r5.device.SaraR5Device

## gpio

Portable digital output lines for devices that toggle SBC/MCU pins (libgpiod /
mcu / null backends), so a device never hard-codes how a pin is driven.

::: core.gpio.make_output_line
::: core.gpio.OutputLine

## effector_base

The base class and registry for effectors. Full API — including concrete plugin
types (`PwmEffector`, `FanArray`, `StreamSink`) — is on the
[effectors reference page](effectors.md).

::: core.effector_base.create_effector

## policy

The base class, `PolicyRuntime`, and registry for policies. Full API — including
concrete plugin types (`CurvePolicy`) — is on the
[policies reference page](policies.md).

::: core.policy.create_policy

## relay

::: core.relay.Relay

## mcu_link

::: core.mcu_link.encode
::: core.mcu_link.decode
::: core.mcu_link.FrameStream
::: core.mcu_link.encode_command
::: core.mcu_link.decode_command

## broadcaster

::: core.broadcaster.Broadcaster

## registry

::: core.registry.register
::: core.registry.create
::: core.registry.registered_types

## models

::: core.models.SensorReading
::: core.models.SensorConfig
::: core.models.ConnectionConfig
::: core.models.SensorChannel
::: core.models.DeviceConfig
::: core.models.EffectorConfig
::: core.models.PolicyConfig
::: core.models.NodeConfig
::: core.models.CameraConfig
::: core.models.NetworkConfig

## config

::: core.config.load_node_config
