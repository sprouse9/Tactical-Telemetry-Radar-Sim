# UDP Telemetry Protocol (PORTS demo)

## Transport
- UDP datagrams
- UTF-8 JSON per datagram (one JSON object per packet)
- Default destination: `127.0.0.1:30001`

## Coordinate + Heading Convention
- 2D local screen/world coordinates for the demo:
  - `x` increases to the right
  - `y` increases downward (screen coordinates)
- Heading degrees:
  - `0°` = up (north)
  - `90°` = right (east)
  - Stored and transmitted normalized to **[0, 360)**

## Message Type: EntityState
The sender publishes one `EntityState` message per entity each tick.

### Fields
- `msg_type` (string): `"EntityState"`
- `entity_id` (int): unique entity identifier
- `entity_type` (string): e.g., `"SUB"`, `"UUV"`, `"SHIP"`, `"BUI"`, `"CONTACT"`
- `x` (float): position (demo units)
- `y` (float): position (demo units)
- `heading_deg` (float): direction of motion in degrees, normalized to [0, 360)
- `speed` (float): speed (demo units/sec)
- `status` (string): `"OK"` or fault/status code
- `seq` (int): monotonically increasing sequence number (shared across entities)
- `timestamp_utc` (string): ISO-8601 UTC timestamp

### Example
```json
{
  "msg_type": "EntityState",
  "entity_id": 1002,
  "entity_type": "UUV",
  "x": 412.3,
  "y": 287.9,
  "heading_deg": 345.0,
  "speed": 2.2,
  "status": "OK",
  "seq": 1234,
  "timestamp_utc": "2026-02-23T22:10:10.123Z"
}