# web/shared/ — shared viewer modules

The common shell every bench viewer in `web/viewers/` builds on. Plain classic
scripts (no bundler) so a viewer is a single self-contained `.html` you open
directly and point at any node's IP.

| File | Provides |
|------|----------|
| `viewer.css` | base dark theme — readout, chart-wrap, conn-bar, status, buttons |
| `stream.js` | `AnimStream.connect({hostInput, sensorId, onReading, onStatus, onNamed})` — SSE client with auto-reconnect |
| `timeseries.js` | `AnimChart.makeLine(canvas, opts)` — Chart.js rolling line chart (`push`, `setMax`, `clear`, `setFormatters`) |
| `heatmap.js` | `AnimHeatmap(canvas, {cols, rows, mirrorX, …})` — grid renderer for array sensors: palette LUT, value-space bilinear or pixel mode, EMA denoise, NaN-aware (missing cells render distinctly), colorbar + crosshair helpers |

A viewer includes these, wires `AnimStream` to its sensor, and renders. The
client owns unit conversion/formatting; the node sends raw SI values.
