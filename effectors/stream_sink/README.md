# stream_sink — reference stream-lane effector

A no-hardware effector that just records the bytes fed to it over the **stream
lane** (`WS /effectors/{id}/stream`). It exists to exercise the continuous-flow
path end to end and to be the template a real streaming effector (speaker audio,
addressable LED-strip animation) follows: implement `feed(chunk)`, set
`lanes = ("stream",)`.

```yaml
effectors:
  - {id: probe, type: stream_sink}
```

`GET /effectors/probe` reports `bytes_received` / `last_chunk`.
