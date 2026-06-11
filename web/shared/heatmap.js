/* AnimHeatmap — shared heatmap engine for array sensors (thermal, pressure).
 *
 * Extracted from the mlx90640 viewer so every grid-shaped sensor renders the
 * same way: palette LUT, value-space bilinear interpolation (interpolate
 * values FIRST, then colour-map — prevents colour-space artefacts), EMA
 * denoising, NaN-aware (missing cells render as the `missing` colour rather
 * than poisoning their neighbours), optional horizontal mirror.
 *
 * Usage:
 *   const hm = new AnimHeatmap(canvas, {cols: 32, rows: 24, mirrorX: true});
 *   hm.push(float32Values);            // marks dirty
 *   hm.render();                       // call from your RAF loop when dirty
 *   hm.setRange(min, max) / setPalette('inferno') / setSmoothing(0.15) ...
 *   const v = hm.valueAt(col, row);    // smoothed value (sensor space)
 *
 * No framework, no build step — <script src="../shared/heatmap.js"> and go.
 */
'use strict';

const ANIM_PALETTES = {
  ironbow:  [[0,0,0],[32,0,48],[64,0,128],[128,0,96],[192,32,0],[255,128,0],[255,224,64],[255,255,192],[255,255,255]],
  inferno:  [[0,0,4],[40,11,84],[101,21,110],[159,42,99],[212,72,66],[245,125,21],[252,193,69],[252,255,164]],
  hot:      [[0,0,0],[192,0,0],[255,64,0],[255,192,0],[255,255,128],[255,255,255]],
  rainbow:  [[0,0,128],[0,0,255],[0,128,255],[0,255,255],[0,255,0],[255,255,0],[255,128,0],[255,0,0],[128,0,0]],
  greyscale:[[0,0,0],[255,255,255]],
};

function animLerpColor(stops, t) {
  t = Math.max(0, Math.min(1, t));
  const n = stops.length - 1;
  const i = Math.floor(t * n);
  const f = t * n - i;
  const a = stops[Math.min(i, n)], b = stops[Math.min(i + 1, n)];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

class AnimHeatmap {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.W = canvas.width;
    this.H = canvas.height;
    this.mirrorX = !!opts.mirrorX;
    this.interpolate = opts.interpolate !== false;
    this.palette = opts.palette || 'ironbow';
    this.missing = opts.missing || [40, 40, 48];   // colour for NaN cells
    this.rangeMin = opts.rangeMin ?? 0;
    this.rangeMax = opts.rangeMax ?? 1;
    // Slider convention: 0 = raw (alpha 1), 1 = max smoothing (alpha → 0).
    this._alpha = 1 - (opts.smoothing ?? 0);
    this._lutSize = 1024;
    this._lut = new Uint8Array(this._lutSize * 3);
    this._buildLUT();
    this.values = null;          // Float32Array, smoothed, sensor-space
    this.dirty = false;
    this.setGrid(opts.cols || 1, opts.rows || 1);
  }

  // ── Configuration ──────────────────────────────────────────────────────────

  setGrid(cols, rows) {
    if (cols === this.cols && rows === this.rows) return;
    this.cols = cols;
    this.rows = rows;
    this.values = null;          // dims changed: restart smoothing
    // Per-output-column source indices + weights (mirror baked in); built once
    // per grid shape, reused by every interpolated frame.
    const W = this.W;
    this._x0 = new Uint16Array(W);
    this._x1 = new Uint16Array(W);
    this._w0 = new Float32Array(W);
    this._w1 = new Float32Array(W);
    for (let px = 0; px < W; px++) {
      const u = px / (W - 1);
      const fx = (this.mirrorX ? 1 - u : u) * (cols - 1);
      const x0 = fx | 0;
      this._x0[px] = x0;
      this._x1[px] = Math.min(x0 + 1, cols - 1);
      this._w1[px] = fx - x0;
      this._w0[px] = 1 - this._w1[px];
    }
    // Offscreen grid-sized canvas for nearest-neighbour (pixel) mode.
    this._off = document.createElement('canvas');
    this._off.width = cols;
    this._off.height = rows;
    this._offCtx = this._off.getContext('2d');
    this.dirty = true;
  }

  setPalette(name) {
    if (!ANIM_PALETTES[name]) return;
    this.palette = name;
    this._buildLUT();
    this.dirty = true;
  }

  setRange(min, max) { this.rangeMin = min; this.rangeMax = max; this.dirty = true; }
  setInterpolate(on) { this.interpolate = !!on; this.dirty = true; }
  setSmoothing(s)    { this._alpha = 1 - Math.max(0, Math.min(1, s)); }

  _buildLUT() {
    const stops = ANIM_PALETTES[this.palette];
    for (let i = 0; i < this._lutSize; i++) {
      const [r, g, b] = animLerpColor(stops, i / (this._lutSize - 1));
      this._lut[i * 3] = r; this._lut[i * 3 + 1] = g; this._lut[i * 3 + 2] = b;
    }
  }

  // ── Data ───────────────────────────────────────────────────────────────────

  push(newValues) {
    const n = this.cols * this.rows;
    if (!this.values || this.values.length !== n) {
      this.values = new Float32Array(newValues.subarray(0, n));
    } else {
      const a = this._alpha, inv = 1 - a, v = this.values;
      for (let i = 0; i < n; i++) {
        const x = newValues[i];
        // NaN-aware EMA: a missing sample keeps the old value class; a sample
        // arriving where none was just takes over (no NaN poisoning).
        v[i] = Number.isNaN(x) ? NaN : (Number.isNaN(v[i]) ? x : a * x + inv * v[i]);
      }
    }
    this.dirty = true;
  }

  /** Smoothed value at sensor-space (col, row) — NaN if missing/unset. */
  valueAt(col, row) {
    if (!this.values || col < 0 || col >= this.cols || row < 0 || row >= this.rows) return NaN;
    return this.values[row * this.cols + col];
  }

  /** Map a mouse event on the canvas to sensor-space {col, row}. */
  cellAt(ev) {
    const rect = this.canvas.getBoundingClientRect();
    const u = (ev.clientX - rect.left) / rect.width;
    const v = (ev.clientY - rect.top) / rect.height;
    let col = Math.floor((this.mirrorX ? 1 - u : u) * this.cols);
    let row = Math.floor(v * this.rows);
    col = Math.max(0, Math.min(this.cols - 1, col));
    row = Math.max(0, Math.min(this.rows - 1, row));
    return { col, row };
  }

  // ── Render (call from a RAF loop; cheap no-op when clean) ─────────────────

  render() {
    if (!this.dirty || !this.values) return false;
    this.dirty = false;
    const { ctx, W, H, cols, rows } = this;
    const mn = this.rangeMin, range = (this.rangeMax - mn) || 1;
    const scale = (this._lutSize - 1) / range;
    const lut = this._lut, miss = this.missing, vals = this.values;

    if (this.interpolate) {
      const imgData = ctx.createImageData(W, H);
      const d = imgData.data;
      for (let py = 0; py < H; py++) {
        const fy = py / (H - 1) * (rows - 1);
        const y0 = fy | 0;
        const y1 = Math.min(y0 + 1, rows - 1);
        const wy1 = fy - y0, wy0 = 1 - wy1;
        const r0 = y0 * cols, r1 = y1 * cols;
        let idx = py * W * 4;
        for (let px = 0; px < W; px++) {
          const s0 = this._x0[px], s1 = this._x1[px];
          const a = vals[r0 + s0], b = vals[r0 + s1];
          const c = vals[r1 + s0], e = vals[r1 + s1];
          const val = a * wy0 * this._w0[px] + b * wy0 * this._w1[px]
                    + c * wy1 * this._w0[px] + e * wy1 * this._w1[px];
          if (Number.isNaN(val)) {              // any missing contributor
            d[idx] = miss[0]; d[idx + 1] = miss[1]; d[idx + 2] = miss[2];
          } else {
            const li = Math.min(this._lutSize - 1, Math.max(0, (val - mn) * scale | 0)) * 3;
            d[idx] = lut[li]; d[idx + 1] = lut[li + 1]; d[idx + 2] = lut[li + 2];
          }
          d[idx + 3] = 255;
          idx += 4;
        }
      }
      ctx.putImageData(imgData, 0, 0);
    } else {
      const imgData = this._offCtx.createImageData(cols, rows);
      const d = imgData.data;
      for (let i = 0; i < cols * rows; i++) {
        const row = (i / cols) | 0;
        const col = i % cols;
        const dst = (row * cols + (this.mirrorX ? cols - 1 - col : col)) << 2;
        const val = vals[i];
        if (Number.isNaN(val)) {
          d[dst] = miss[0]; d[dst + 1] = miss[1]; d[dst + 2] = miss[2];
        } else {
          const li = Math.min(this._lutSize - 1, Math.max(0, (val - mn) * scale | 0)) * 3;
          d[dst] = lut[li]; d[dst + 1] = lut[li + 1]; d[dst + 2] = lut[li + 2];
        }
        d[dst + 3] = 255;
      }
      this._offCtx.putImageData(imgData, 0, 0);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(this._off, 0, 0, W, H);
    }
    return true;
  }

  /** Paint a horizontal palette colourbar onto another canvas. */
  drawColorbar(barCanvas) {
    const w = barCanvas.width, h = barCanvas.height;
    const bctx = barCanvas.getContext('2d');
    for (let x = 0; x < w; x++) {
      const [r, g, b] = animLerpColor(ANIM_PALETTES[this.palette], x / (w - 1));
      bctx.fillStyle = `rgb(${r},${g},${b})`;
      bctx.fillRect(x, 0, 1, h);
    }
  }

  /** Crosshair overlay helper: draw at sensor-space (col, row) on `overlay`. */
  drawCrosshair(overlay, col, row) {
    const ox = overlay.getContext('2d');
    ox.clearRect(0, 0, overlay.width, overlay.height);
    if (col < 0 || row < 0) return;
    const u = (col + 0.5) / this.cols;
    const x = (this.mirrorX ? 1 - u : u) * overlay.width;
    const y = (row + 0.5) / this.rows * overlay.height;
    const s = 12;
    ox.strokeStyle = 'rgba(255,204,68,0.85)'; ox.lineWidth = 1.5;
    ox.beginPath();
    ox.moveTo(x - s, y); ox.lineTo(x + s, y);
    ox.moveTo(x, y - s); ox.lineTo(x, y + s);
    ox.stroke();
    ox.strokeStyle = 'rgba(255,204,68,0.3)'; ox.lineWidth = 1;
    ox.beginPath(); ox.arc(x, y, 16, 0, Math.PI * 2); ox.stroke();
  }
}
