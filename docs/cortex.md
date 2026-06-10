# The Cortex Runtime — devices, sensors, effectors, policies

Each node is a **cortex**: a specialized region (vision, auditory, proprioception,
somatosensory, logical analysis, power control, …) with local input, output, and
control. This page describes the node runtime that makes it one. For the firmware
that feeds it, see [Firmware & Targets (forge)](forge.md); for the fleet, see
[Architecture](architecture.md).

## The tiers

```
                     ┌──────────── relay (thalamus): named-signal pub/sub + gating ───────────┐
   afferent ─────────┴────────────────────────────────────────────────────────────────────────┘──── efferent
   devices ──► sensors ─┐                                                          ┌─► effectors ──► devices
                        ├─► observation ──► POLICY (stack: reflex + cortical) ────►┤
   models  ─────────────┘     (relay signals)     step(obs) → action                action (effector channels)
```

Held on `app.state` and created in `node/app.py`'s lifespan (devices → sensors →
effectors → relay → policies; stopped in reverse).

| Tier | Role | Where |
| --- | --- | --- |
| **device** | shared peripheral (MCU link, ADS1115 chip, SARA-R5 modem); sensors read it, effectors write it | base in `core/device.py`; kinds in `devices/` |
| **sensor** | afferent → raw signals; may span devices (one logical sensor over 4 MCUs) | `core/sensor_base.py`, `core/analog_array.py` |
| **model** | learned *perception* (signals → features); a forge/accelerator artifact — an "advanced sensor" | *seam (future)* |
| **effector** | efferent output (motion/light/sound); type-defined drive, two lanes | `core/effector_base.py` + `effectors/` |
| **policy** | control loop (observation → action); composable, swappable, light | `core/policy.py` + `policies/` |
| **relay** | the thalamus: named-signal pub/sub + gating; the inter-cortex seam | `core/relay.py` |

One boundary holds across all of it: **devices move bytes; sensors, models,
effectors, and policies own all meaning.**

## Devices — shared peripherals

A device owns a transport that's shared across directions or sensors, so neither a
sensor nor an effector owns it. Concrete kinds live in the `devices/` plugin tree
(base + registry + factory in `core/device.py`), auto-discovered like sensors:
`mcu_serial` (push: a read pump decodes [`core/mcu_link.py`](forge.md) frames and
fans them to subscribers; `send_command` sends back), `ads1115` (pull: serialized
muxed single-shot reads), `sara_r5` (mixed: pushes NMEA to GNSS subscribers, polls
LTE status via AT). Declared in `config/boards/<id>.yaml` under `devices:` and
bound to sensors/effectors by id. Pins a device toggles go through the portable
`core/gpio.py` output-line abstraction, never hard-coded sysfs.

## Sensors — logical, possibly multi-device

`AnalogArrayBase` binds to one or more devices and maps each channel
`(device, index) → signal + calibration`, composing one reading. So
`mq_array` (one MCU) and the `cranial_pressure` surface (`pressure_array` over 4
MCUs × 4 ADS1115 = 64 channels) are both single logical sensors — devices are
metadata, organization is logical. Scalar `analog_in` reads heterogeneous channels
through an `Ads1115Device`; `board_temp` reads SBC thermal zones (no device).

## Effectors — typed output, two lanes

Not "actuators": effectors cover motion, light, and sound. Each *type* defines its
own drive (no universal verb) over the lane(s) it supports:

- **request** lane — an occasional value that holds (`PwmEffector`: named-channel
  levels `0.0–1.0`, scaled to the device's command; optional `params.min_duty`
  maps a non-zero level into `[min_duty, 1]` so high-rpm fans start). `POST /effectors/{id}`.
- **stream** lane — a continuous flow (speaker audio, LED-strip animation).
  `WS /effectors/{id}/stream` (reference `StreamSink` today; real hardware later).

Declared under `effectors:`; `backend: {device: <id>}` writes through a device.
This is where the fans live — driven through the MCU device, never the gas sensor.

## Policies — the control loop

A policy maps an **observation** (named relay signals) to an **action** (effector
channels): `step(obs) → action`. Behavior is *code, not config* — a registered
`PolicyBase` (today a hand-written `CurvePolicy`, later a learned/stochastic model)
behind one contract, so a reflex and a neural net are interchangeable. `PolicyConfig`
declares only the observation/action wiring + params.

- **Reflexes are always-on policies.** The fan loop is an always-on `curve` that
  drives the fans on the worse of gas and board temperature, fail-safe low on a
  missing input — it keeps cooling even while cortical policies are down or being
  hot-swapped.
- **Composable stack.** `PolicyRuntime` ticks the stack (always-on first), each
  tick: snapshot sensors → relay → build each policy's observation → `step` → drive
  its effector. `GET /policies`, `POST /policies/{id}/enable`.

Policies *use* models (perception); they are not models. Control lives on the
**closest node** to the effectors it drives.

## Relay — the thalamus (and the inter-cortex seam)

`core/relay.py` is an in-process, latest-value pub/sub keyed by dotted names
(`gas_array.raw.mq135`, `board_temp.cpu_c`) with a gating hook (attention).
Policies read observations from it; sensor readings are flattened into it each
tick. Today it is local; it is the seam for the brain-inspired substrate to come:
**cross-node delivery + declared reciprocal predict-down / error-up tracts**
between cortices (predictive coding / active inference). A fleet aggregator will
nest the node trees by cortex.

## API (node-implicit, logical)

```
/sensors    /sensors/{id}    (+ /stream SSE, /frames WS)
/effectors  /effectors/{id}  (+ POST request lane, WS /stream lane)
/policies   /policies/{id}   (+ POST /{id}/enable)
```

The node is implicit locally; devices are metadata, never a path segment.

## Status

Built: devices (MCU + ADS1115), logical array sensors, effectors (request +
stream lanes), policies + relay + the always-on fan reflex, and the
`mcu/circuit_python` forge family feeding `pressure_array`. Reserved behind seams:
the **models** tier (accelerator perception nets via forge), **learned/stochastic
policies** + on-device training, **cross-node relay + predict/error tracts**, the
fleet aggregator, and concrete stream-lane hardware (speakers, LED strips). See
`TODO.md`.
