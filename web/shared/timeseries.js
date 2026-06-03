/*
 * AnimChart — shared rolling line-chart for scalar/timeseries sensors.
 *
 * Classic script (loads over file://). Requires Chart.js 4 to be loaded first.
 * Exposes window.AnimChart.
 *
 * Wraps the Chart.js boilerplate + the fixed-length ring buffer that every
 * distance viewer was reimplementing. The caller owns unit conversion and
 * supplies already-converted display values to push().
 */
(function () {
  "use strict";

  /**
   * Create a rolling line chart.
   *
   * canvasEl  — <canvas> element
   * opts:
   *   color     string  — line / fill colour (default GitHub blue)
   *   max       number  — initial Y-axis max (display units)
   *   history   number  — number of points retained (default 60)
   *   tickFmt   fn(v)   — axis tick formatter
   *   tipFmt    fn(v)   — tooltip formatter
   *
   * Returns:
   *   push(v)        — append one display value (null = gap)
   *   setMax(m)      — change Y-axis max
   *   setFormatters(tickFmt, tipFmt)
   *   clear()        — blank the buffer (e.g. on unit change)
   */
  function makeLine(canvasEl, opts) {
    opts = opts || {};
    const color = opts.color || "#58a6ff";
    const fill = opts.fill || "rgba(88,166,255,0.08)";
    const HISTORY = opts.history || 60;
    let tickFmt = opts.tickFmt || ((v) => String(v));
    let tipFmt = opts.tipFmt || ((v) => String(v));

    const data = Array(HISTORY).fill(null);

    const chart = new Chart(canvasEl, {
      type: "line",
      data: {
        labels: Array(HISTORY).fill(""),
        datasets: [{
          data,
          borderColor: color,
          backgroundColor: fill,
          borderWidth: 2,
          pointRadius: 0,
          fill: true,
          tension: 0.3,
          spanGaps: true,
        }],
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { display: false },
          y: {
            min: 0,
            max: opts.max,
            ticks: { color: "#8b949e", callback: (v) => tickFmt(v) },
            grid: { color: "#21262d" },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => tipFmt(ctx.parsed.y) } },
        },
      },
    });

    function redraw() {
      chart.data.datasets[0].data = [...data];
      chart.update("none");
    }

    return {
      push(v) {
        data.push(v);
        if (data.length > HISTORY) data.shift();
        redraw();
      },
      setMax(m) {
        chart.options.scales.y.max = m;
        chart.update("none");
      },
      setFormatters(tf, pf) {
        if (tf) tickFmt = tf;
        if (pf) tipFmt = pf;
        chart.options.scales.y.ticks.callback = (v) => tickFmt(v);
        chart.update("none");
      },
      clear() {
        data.fill(null);
        redraw();
      },
    };
  }

  window.AnimChart = { makeLine };
})();
