from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
import os

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────
# In-memory state (no database needed)
# ─────────────────────────────────────────
devices = {}
# devices["tracker_01"] = {
#   "lat": 0.0, "lng": 0.0, "speed": 0.0,
#   "altitude": 0.0, "satellites": 0,
#   "gps_fixed": False, "relay_state": "on",
#   "last_seen": datetime,
#   "command": "none"   ← "none" | "cut" | "restore"
# }

# ─────────────────────────────────────────
# ESP8266 endpoints
# ─────────────────────────────────────────

@app.route("/api/gps", methods=["POST"])
def receive_gps():
    """ESP8266 pushes GPS data here every 3 seconds.

    Accepts BOTH naming conventions so the firmware can use short field
    names (sats, valid, alt) without the backend losing data:
        sats      | satellites
        valid     | gps_fixed
        alt       | altitude
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    device_id = data.get("device_id", "unknown")

    if device_id not in devices:
        devices[device_id] = {"command": "none", "relay_state": "on"}

    devices[device_id].update({
        "lat":         data.get("lat", 0.0),
        "lng":         data.get("lng", 0.0),
        "speed":       data.get("speed", 0.0),
        "altitude":    data.get("alt",   data.get("altitude", 0.0)),
        "satellites":  data.get("sats",  data.get("satellites", 0)),
        "gps_fixed":   data.get("valid", data.get("gps_fixed", False)),
        "relay_state": data.get("relay_state", devices[device_id].get("relay_state", "on")),
        "last_seen":   datetime.now(timezone.utc).isoformat(),
    })

    return jsonify({"status": "ok"}), 200


@app.route("/api/command", methods=["GET"])
def get_command():
    """ESP8266 polls here every 2 seconds for pending commands."""
    device_id = request.args.get("device_id", "unknown")

    if device_id not in devices:
        return jsonify({"command": "none"}), 200

    command = devices[device_id].get("command", "none")

    # Clear command after delivering it so it only executes once
    if command in ("cut", "restore"):
        devices[device_id]["command"] = "none"

    return jsonify({"command": command}), 200


# ─────────────────────────────────────────
# Dashboard endpoints
# ─────────────────────────────────────────

@app.route("/api/status", methods=["GET"])
def get_status():
    """Dashboard polls this for live device data."""
    device_id = request.args.get("device_id", "tracker_01")

    if device_id not in devices:
        return jsonify({"online": False}), 200

    d = devices[device_id]
    last_seen = d.get("last_seen")

    # Determine online status (offline if no update in 10 seconds)
    online = False
    if last_seen:
        last_dt = datetime.fromisoformat(last_seen)
        diff = (datetime.now(timezone.utc) - last_dt).total_seconds()
        online = diff < 10

    return jsonify({
        "online":      online,
        "lat":         d.get("lat", 0.0),
        "lng":         d.get("lng", 0.0),
        "speed":       d.get("speed", 0.0),
        "altitude":    d.get("altitude", 0.0),
        "satellites":  d.get("satellites", 0),
        "gps_fixed":   d.get("gps_fixed", False),
        "relay_state": d.get("relay_state", "on"),
        "last_seen":   last_seen,
    }), 200


@app.route("/api/control", methods=["POST"])
def send_command():
    """Dashboard sends cut/restore command here."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    device_id = data.get("device_id", "tracker_01")
    command   = data.get("command", "none")

    if command not in ("cut", "restore", "none"):
        return jsonify({"error": "Invalid command"}), 400

    if device_id not in devices:
        devices[device_id] = {}

    devices[device_id]["command"] = command
    print(f"[CTRL] Command '{command}' queued for device '{device_id}'")

    return jsonify({"status": "queued", "command": command}), 200


@app.route("/api/devices", methods=["GET"])
def list_devices():
    """List all known devices."""
    result = {}
    for device_id, d in devices.items():
        last_seen = d.get("last_seen")
        online = False
        if last_seen:
            last_dt = datetime.fromisoformat(last_seen)
            diff = (datetime.now(timezone.utc) - last_dt).total_seconds()
            online = diff < 10
        result[device_id] = {"online": online, "last_seen": last_seen}
    return jsonify(result), 200


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "GPS Tracker Server running"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
