# web/viewers/ — per-sensor bench viewers

One self-contained `<type>.html` per sensor, built on [`web/shared/`](../shared/README.md).
They are dev-machine diagnostics — open the file in a browser, enter a node's IP +
sensor id, and watch live data. They live here (not in the sensor packages) because
they're opened from a dev machine against any node and share one shell.

Archetypes to copy from:

- **scalar / timeseries** — `tf_mini.html` (distance + rolling chart; JSON SSE lane).
- **heatmap over the binary frame lane** — `mlx90640.html` (`/sensors/{id}/frames` WS).
- **multi-channel** — `mq_array.html` (a card + sparkline per discovered signal).

A new sensor's viewer is step 6 of the [add-a-sensor checklist](../../CLAUDE.md).
(Effector-control and `pressure_array` viewers are still TODO.)
