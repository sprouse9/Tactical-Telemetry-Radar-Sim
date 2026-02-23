# PORTS Tactical Sim Demo (UDP + Pygame)

A small distributed simulation demo:
- **sender.py** publishes multi-entity telemetry over UDP (JSON datagrams)
- **receiver_ui.py** renders a radar-style display (tracks, vectors, stale detection)

## Quick Start

Terminal A (receiver UI):
- `python receiver_ui.py`

Terminal B (sender):
- `python sender.py --entities 8 --hz 20`

## Controls (receiver_ui.py)
- **H**: toggle trails
- **V**: toggle heading vectors
- **L**: toggle labels

## Notes
- Default UDP: `127.0.0.1:30001`
- One UDP datagram = one JSON message
- Message schema and coordinate conventions are documented in **protocol.md**