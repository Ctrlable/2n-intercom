# 2N Intercom for Home Assistant

A Home Assistant custom integration for **2N IP intercoms and access units** — switch/relay control, IO input monitoring, directory management, real-time log events, and Keymaster synchronisation. Zero external dependencies.

---

## Features

- **Switch / relay control** — exposes 2N relays and switches as HA `switch` entities
- **IO input monitoring** — binary sensors for each IO input (motion, doorbell contact, tamper, etc.)
- **Directory CRUD** — create, update, and delete directory users via HA services
- **PIN and switch code management** — set, clear, and rotate PINs and up to 4 switch codes per user
- **Real-time log events** — long-poll event loop fires `2n_intercom_doorbell`, `2n_intercom_access_granted`, `2n_intercom_access_denied`, and `2n_intercom_call_state` events into HA
- **Keymaster bridge** — automatic code sync from [keymaster](https://github.com/FutureTense/keymaster) to 2N switch code slots
- **System sensor** — uptime and device info sensor
- **Config Flow** — fully UI-driven setup, no YAML editing required
- **Multi-device** — each 2N device is a separate config entry
- **Zero external dependencies** — native async HTTP API client, no extra Python packages
- **HACS compatible**

---

## Requirements

- Home Assistant 2023.1+
- A 2N IP intercom or access unit with firmware supporting the HTTP API
- HTTP API enabled on the device: **Device web UI → Services → HTTP API**
- An API account with read/write privileges for the features you need

---

## Installation

### Via HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/Ctrlable/2n-intercom` as type **Integration**
3. Install **2N Intercom**
4. Restart Home Assistant

### Manual

1. Copy `custom_components/2n_intercom/` into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **2N Intercom**
3. Fill in the device IP, API credentials, and optional settings (HTTPS, SSL verify, port, name)

---

## Entities

| Domain | Entity | Description |
|---|---|---|
| `switch` | `switch.<device>_relay_<n>` | Each relay/switch output |
| `binary_sensor` | `binary_sensor.<device>_io_<n>` | Each IO input |
| `sensor` | `sensor.<device>_system` | Device uptime and info |

---

## Events

| Event | Fired when |
|---|---|
| `2n_intercom_doorbell` | Doorbell button pressed |
| `2n_intercom_access_granted` | Valid credential presented |
| `2n_intercom_access_denied` | Invalid credential presented |
| `2n_intercom_call_state` | Active call state change |

---

## Keymaster Integration

When [keymaster](https://github.com/FutureTense/keymaster) is also installed, the bridge activates automatically. Keymaster slot names must match 2N directory user names (case-insensitive) for codes to sync.

---

## License

MIT
