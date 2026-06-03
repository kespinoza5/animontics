/*
 * AnimStream — shared connection helper for the Animontics node API.
 *
 * Classic script (no ES module import/export) so it loads over file:// without
 * the CORS restrictions browsers place on module scripts. Exposes a single
 * global: window.AnimStream.
 *
 * The node serves Server-Sent Events at:
 *     http://<host>:<port>/sensors/<sensorId>/stream
 * Each event's data is a JSON-encoded SensorReading:
 *     { sensor_id, sensor_type, timestamp, data: { ... } }
 * Sensor-specific control state (e.g. vl53l1x range mode) arrives as named SSE
 * events, surfaced via the onNamed callback.
 */
(function () {
  "use strict";

  const DEFAULT_PORT = 8080;
  const RECONNECT_MS = 3000;

  /**
   * Open a resilient SSE connection to one sensor.
   *
   * opts:
   *   host       string   — board IP / hostname (read live on each reconnect)
   *   port       number   — node port (default 8080)
   *   sensorId   string   — sensor id as configured on the node
   *   onReading  fn(data, reading) — data = reading.data; reading = full envelope
   *   onStatus   fn(text, cls)     — cls is '' | 'ok' | 'err'
   *   onNamed    fn(eventName, parsedData)  — optional, for named SSE events
   *   hostInput  HTMLInputElement  — optional; if given, host is read from it live
   *
   * Returns { reconnect(), close() }.
   */
  function connect(opts) {
    const port = opts.port || DEFAULT_PORT;
    const namedEvents = opts.namedEvents || [];
    let active = null;
    let closed = false;

    const status = (text, cls) => { if (opts.onStatus) opts.onStatus(text, cls); };
    const host = () =>
      (opts.hostInput ? opts.hostInput.value : opts.host || "").trim();

    function open() {
      if (closed) return;
      if (active) active.close();

      const h = host();
      status(`connecting to ${h}…`, "");

      const es = new EventSource(
        `http://${h}:${port}/sensors/${opts.sensorId}/stream`
      );
      active = es;

      es.onopen = () => status("live", "ok");

      es.onmessage = (e) => {
        let reading;
        try { reading = JSON.parse(e.data); } catch { return; }
        const data = reading && reading.data;
        if (data && opts.onReading) opts.onReading(data, reading);
      };

      namedEvents.forEach((name) => {
        es.addEventListener(name, (e) => {
          if (!opts.onNamed) return;
          let parsed;
          try { parsed = JSON.parse(e.data); } catch { return; }
          opts.onNamed(name, parsed);
        });
      });

      es.onerror = () => {
        if (es !== active) return;             // stale handler from a prior socket
        status("disconnected — reconnecting…", "err");
        es.close();
        active = null;
        if (!closed) setTimeout(open, RECONNECT_MS);
      };
    }

    open();

    return {
      reconnect: open,
      close() { closed = true; if (active) active.close(); active = null; },
    };
  }

  window.AnimStream = { connect, DEFAULT_PORT };
})();
