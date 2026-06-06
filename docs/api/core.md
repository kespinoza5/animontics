# core — API Reference

The `core` package is the **cortex runtime** plus shared infrastructure. No
hardware dependencies — importable on any machine (hardware libs load lazily).

## sensor_base

::: core.sensor_base.SensorBase

## analog_array

::: core.analog_array.AnalogArrayBase

## device

::: core.device.Device
::: core.device.McuSerialDevice
::: core.device.Ads1115Device
::: core.device.create_device

## effector_base

::: core.effector_base.EffectorBase
::: core.effector_base.PwmEffector
::: core.effector_base.create_effector

## policy

::: core.policy.PolicyBase
::: core.policy.CurvePolicy
::: core.policy.PolicyRuntime
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
