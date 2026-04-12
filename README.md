# 2N Intercom for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/YOUR_USERNAME/2n-intercom.svg)](https://github.com/YOUR_USERNAME/2n-intercom/releases)

Full Home Assistant integration for **2N IP intercoms and access units**.  
Zero external dependencies — replaces `helios2n-hass` with more features.

---

## Features

- 🔒 **Switch / relay control** — switch entities with on/off/trigger
- 🔌 **IO input monitoring** — binary sensor entities for door contacts, tamper, etc.
- 📷 **Camera** — live JPEG snapshot entity (internal camera only, skips disabled external)
- 👤 **Directory CRUD** — create, update, delete users via services
- 🔑 **PIN & switch code management** — set/clear PIN and up to 4 switch codes per user
- 📡 **Real-time log events** — doorbell press, access granted/denied, call state changes
- 🗂️ **Keymaster bridge** — auto-syncs Keymaster slot codes to 2N switch codes
- 📊 **System sensor** — uptime, firmware, model info
- 🃏 **Lovelace card** — full user management UI with camera feed

---

## Installation

### Via HACS (recommended)

#### Integration
1. Open HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/YOUR_USERNAME/2n-intercom`  category: **Integration**
3. Install **2N Intercom**
4. Restart Home Assistant

#### Lovelace Card
1. Open HACS → Frontend → ⋮ → Custom repositories
2. Add `https://github.com/YOUR_USERNAME/2n-intercom`  category: **Dashboard**
3. Install **2N Intercom**
4. The resource `/hacsfiles/2n-intercom/2n-intercom.js` is added automatically

### Manual
Copy `custom_components/2n_intercom/` to your HA `config/custom_components/` folder.  
Copy `dist/2n-intercom.js` to `/config/www/` and add as a resource.

---

## Setup

1. **Settings → Devices & Services → Add Integration → 2N Intercom**
2. Enter your device IP, API username and password
3. Enable HTTP API on the device: **Services → HTTP API** — enable System, Switch, IO, Camera, Log, Directory services

---

## Lovelace Card

```yaml
type: custom:2n-intercom-card
entity_prefix: "front_door"      # part of your entity names — check Developer Tools → States
title: "Front Door Intercom"
show_camera: true
```

The card auto-detects your camera, switch, and user entities based on the prefix.

---

## Services

| Service | Description |
|---|---|
| `2n_intercom.create_user` | Create a new directory user |
| `2n_intercom.update_user` | Update an existing user by UUID |
| `2n_intercom.delete_user` | Delete a user by UUID |
| `2n_intercom.set_pin` | Set a user's PIN code |
| `2n_intercom.clear_pin` | Clear a user's PIN |
| `2n_intercom.set_switch_codes` | Set up to 4 switch codes |
| `2n_intercom.set_access_validity` | Set access valid from/to timestamps |
| `2n_intercom.sync_from_keymaster` | Manually sync a Keymaster slot code |
| `2n_intercom.trigger_switch` | Trigger a switch (on/off/trigger) |
| `2n_intercom.restart_device` | Restart the 2N device |
| `2n_intercom.audio_test` | Play audio test on device |

---

## Events

| Event | When |
|---|---|
| `2n_intercom_doorbell` | Button pressed on device |
| `2n_intercom_access_granted` | Card, PIN or fingerprint accepted |
| `2n_intercom_access_denied` | Card, PIN or fingerprint rejected |
| `2n_intercom_call_state` | Call started/ended |
| `2n_intercom_device_log` | Any device log event (catch-all) |
| `2n_intercom_user_created` | Directory user created via service |
| `2n_intercom_user_updated` | Directory user updated via service |
| `2n_intercom_user_deleted` | Directory user deleted via service |
| `2n_intercom_code_changed` | PIN or switch code changed |

---

## 2N Device Prerequisites

Enable these services in the device web UI under **Services → HTTP API**:

| Service | Required for |
|---|---|
| System | Connection test, uptime sensor |
| Switch | Switch entities |
| IO | Binary sensor entities |
| Camera | Camera entity |
| Logging | Real-time events (doorbell, access) |
| Directory | User management |

Set authentication to **Basic** and create an API user with appropriate privileges.

---

## Keymaster Integration

When [keymaster](https://github.com/FutureTense/keymaster) is installed, codes sync automatically:
- Keymaster slot name must match the 2N directory user name (case-insensitive)
- Slot 1 → Switch code slot 1, Slot 2 → slot 2, etc.

---

## License

MIT
