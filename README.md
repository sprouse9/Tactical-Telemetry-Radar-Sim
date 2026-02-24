# PORTS Tactical Simulation Demo (UDP + Pygame)

https://github.com/user-attachments/assets/aab41ca1-fe54-4374-993b-74958d4132dc

A lightweight distributed simulation demo modeling real-time tactical track updates over UDP.

The system simulates multiple moving entities broadcasting telemetry, while a separate receiver renders a radar-style display with track vectors, labels, and stale detection.

---

## Overview

This project explores core concepts found in distributed training and tactical simulation systems:

- Real-time state synchronization
- Stateless UDP telemetry transport
- Multi-entity tracking
- Track lifecycle management
- Radar-style visualization
- Stale track detection

The architecture intentionally separates simulation (sender) from visualization (receiver), mirroring real-world distributed simulation pipelines.

---

## System Architecture

The application consists of two independent components communicating via UDP:

Sender  →  UDP Telemetry  →  Receiver UI

This separation allows simulation logic and visualization logic to evolve independently.

---

## Components

### sender.py

Publishes multi-entity telemetry over UDP using JSON datagrams.

Each entity transmits:
- Entity ID
- Position (x, y)
- Heading (degrees)
- Speed (units/sec)
- Timestamp

Configurable parameters:
- `--entities` → number of simulated tracks
- `--hz` → update frequency (broadcast rate)

Example:
```
python sender.py --entities 8 --hz 20
```

---

### receiver_ui.py

- Non-blocking UDP listener
- Parses JSON datagrams
- Maintains per-track state
- Renders radar-style visualization using Pygame
- Flags stale tracks when updates stop arriving

Features:
- Heading vectors
- Track trails
- Toggleable labels
- Real-time multi-entity display

---

## Quick Start

Terminal A (Receiver UI):
```
python receiver_ui.py
```

Terminal B (Sender):
```
python sender.py --entities 8 --hz 20
```

---

## Controls (receiver_ui.py)

- **H** → Toggle trails  
- **V** → Toggle heading vectors  
- **L** → Toggle labels  

---

## Network Details

- Default UDP endpoint: `127.0.0.1:30001`
- One UDP datagram = one JSON message
- Message schema and coordinate conventions are documented in `protocol.md`

---

## Design Intent

This demo was built to explore foundational principles behind distributed tactical simulation systems, including:

- Decoupled simulation and rendering
- UDP-based telemetry transport
- Real-time track management
- Visualization pipelines for moving entities

The architecture can be extended toward:

- Packet loss simulation
- Artificial latency injection
- Predictive motion modeling
- Bearing-rate visualization
- Alternative UI front-ends (WinForms, Qt, etc.)

---

## Author

Randy Sprouse  
M.S. Data Science  
Focused on distributed simulation, state modeling, and real-time systems
