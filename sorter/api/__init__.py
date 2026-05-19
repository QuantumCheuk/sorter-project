# sorter/api/__init__.py
# REST API server for HUSKY-SORTER-001
# Author: Little Husky 🐕 | Date: 2026-04-26

"""
Flask REST API for HUSKY-SORTER-001
====================================
Provides HTTP endpoints for:
- System status (GET /status)
- Bin levels (GET /bins)
- Current batch (GET /batch/current)
- Configuration (GET/PUT /config)
- Calibration (POST /calibration/*)
- Control (POST /control/*)

Run: python -m sorter.api
Default: http://0.0.0.0:5000
"""

from flask import Flask, jsonify, request, abort
import functools
import hashlib
import os
import secrets
import threading
import time
import json

app = Flask(__name__)

# ============================================================
# API Key Authentication (P0-023 fix, v2 2026-05-17)
# ============================================================

_API_KEYS: dict = {}  # key_hash → {"name": str, "created": str, "last_used": float}
_API_KEYS_LOCK = threading.Lock()
_VALID_BINS = {"A1", "A2", "A3", "B1", "B2", "C1", "C2", "BF"}
_VALID_MOTORS = {"vibrating_feeder", "size_sorter", "spiral_feeder", "rotary_distributor"}
_MOTOR_RPM_RANGE = {
    "vibrating_feeder": (10, 200),
    "size_sorter": (5, 60),
    "spiral_feeder": (10, 200),
    "rotary_distributor": (5, 60),
}


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def init_api_keys(keys: list = None):
    """Load API keys from env or generate defaults.

    Keys can be set via SORTER_API_KEYS env var (comma-separated).
    If not set, a random key is generated and printed to stdout.
    """
    global _API_KEYS
    with _API_KEYS_LOCK:
        if keys:
            for k in keys:
                _API_KEYS[_hash_key(k)] = {
                    "name": k[:8] + "...",
                    "created": time.strftime("%Y-%m-%d"),
                    "last_used": 0,
                }
            return

        env_keys = os.environ.get("SORTER_API_KEYS", "")
        if env_keys:
            for k in env_keys.split(","):
                k = k.strip()
                if k:
                    _API_KEYS[_hash_key(k)] = {
                        "name": k[:8] + "...",
                        "created": time.strftime("%Y-%m-%d"),
                        "last_used": 0,
                    }
            print(f"[API] Loaded {len(_API_KEYS)} API keys from SORTER_API_KEYS")
            return

        # Generate a random key
        random_key = secrets.token_urlsafe(32)
        _API_KEYS[_hash_key(random_key)] = {
            "name": "default",
            "created": time.strftime("%Y-%m-%d"),
            "last_used": 0,
        }
        print(f"[API] ⚠ No SORTER_API_KEYS set. Generated random key:")
        print(f"[API]   {random_key}")
        print(f"[API] Set SORTER_API_KEYS env var to persist keys across restarts.")


def require_api_key(f):
    """Decorator: require valid API key in X-API-Key header."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_required = os.environ.get("SORTER_API_AUTH_REQUIRED", "true").lower() in ("1", "true", "yes")
        if not auth_required:
            return f(*args, **kwargs)

        key = request.headers.get("X-API-Key", "")
        if not key:
            return jsonify({"status": "error", "message": "X-API-Key header required"}), 401

        key_hash = _hash_key(key)
        with _API_KEYS_LOCK:
            if key_hash not in _API_KEYS:
                return jsonify({"status": "error", "message": "Invalid API key"}), 403
            _API_KEYS[key_hash]["last_used"] = time.time()

        return f(*args, **kwargs)

    return decorated


def get_api_keys_info() -> list:
    """List registered API keys (name, created, last_used)."""
    with _API_KEYS_LOCK:
        return list(_API_KEYS.values())

# ============================================================
# System state (injected from main sorter process)
# In production these would be shared via a proper IPC/RPC layer
# For now we use a thread-safe state dict
# ============================================================

class SystemState:
    """Thread-safe system state registry."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance
    
    def _init(self):
        self._state = {
            "uptime_s": 0,
            "active": False,
            "throughput_kg_h": 0.0,
            "state": "idle",
            "mqtt_connected": False,
            "mqtt_msgs_sent": 0,
            "mqtt_msgs_received": 0,
            "current_batch": None,
            "bins": {
                "A1": 0.0, "A2": 0.0, "A3": 0.0,
                "B1": 0.0, "B2": 0.0,
                "C1": 0.0, "C2": 0.0,
                "BF": 0.0,
            },
            "config": self._default_config(),
            "sensors": {
                "load_cell": {"connected": False, "reading_g": None},
                "moisture": {"connected": False, "reading_pct": None},
                "density": {"connected": False, "grade": None},
            },
            "motors": {
                "vibrating_feeder": {"enabled": False, "rpm": 0},
                "size_sorter": {"enabled": False, "position": 0},
                "spiral_feeder": {"enabled": False, "rpm": 0},
                "rotary_distributor": {"enabled": False, "position": "A1"},
            },
        }
        self._start_time = time.time()
    
    def _default_config(self):
        return {
            "target_throughput_kg_h": 2.0,
            "batch_size_g": 250,
            "quality_thresholds": {"A": 85, "B": 70, "C": 50},
            "moisture_range_min_pct": 5.0,
            "moisture_range_max_pct": 15.0,
            "mqtt_broker": "mqtt.local",
            "mqtt_keepalive_s": 60,
        }
    
    def get_all(self):
        with self._lock:
            state = dict(self._state)
            state["uptime_s"] = round(time.time() - self._start_time, 1)
            return state
    
    def update(self, updates):
        with self._lock:
            self._state.update(updates)
    
    def get_bin_levels(self):
        with self._lock:
            return dict(self._state["bins"])
    
    def set_bin_level(self, bin_id, level_g):
        with self._lock:
            if bin_id in self._state["bins"]:
                self._state["bins"][bin_id] = round(level_g, 1)
    
    def get_config(self):
        with self._lock:
            return dict(self._state["config"])
    
    def update_config(self, updates):
        with self._lock:
            self._state["config"].update(updates)
            return dict(self._state["config"])
    
    def get_sensor_reading(self, sensor):
        with self._lock:
            return dict(self._state["sensors"].get(sensor, {}))
    
    def update_sensor(self, sensor, data):
        with self._lock:
            if sensor in self._state["sensors"]:
                self._state["sensors"][sensor].update(data)
    
    def get_motor_state(self, motor):
        with self._lock:
            return dict(self._state["motors"].get(motor, {}))

# Global state
_state = SystemState()

# P1-09 fix: optional SorterController reference for real hardware mode
# When set, read endpoints proxy to controller; write endpoints call controller
_controller = None  # type: Optional[Any]


def inject_controller(sorter_controller):
    """Inject the real SorterController instance.

    Call this from main.py after creating the controller:
        from sorter.api import inject_controller
        inject_controller(controller)
    """
    global _controller
    _controller = sorter_controller
    print("[API] SorterController injected — API now proxies to real controller")


# ============================================================
# Utility helpers
# ============================================================

def ok(data=None, **kwargs):
    """Return successful JSON response."""
    payload = kwargs if kwargs else {}
    if data is not None:
        payload["data"] = data
    return jsonify({"status": "ok", **payload})

def error(msg, code=400):
    abort(code or 400)


# ============================================================
# Health / Status
# ============================================================

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return ok({"healthy": True, "timestamp": time.time()})

@app.route("/status", methods=["GET"])
def status():
    """Full system status. P1-09: reads from real controller when injected."""
    if _controller is not None:
        try:
            ctrl_status = _controller.get_status()
            return ok({
                "state": ctrl_status.get("state", "UNKNOWN"),
                "substate": ctrl_status.get("substate", ""),
                "active": _controller._running,
                "stats": ctrl_status.get("stats", {}),
                "current_batch": ctrl_status.get("current_batch"),
                "buffer_size": ctrl_status.get("buffer_size", 0),
                "controller_connected": True,
            })
        except Exception as e:
            return ok({"error": f"Controller error: {e}", "controller_connected": False})
    s = _state.get_all()
    return ok({
        "uptime_s": s["uptime_s"],
        "active": s["active"],
        "state": s["state"],
        "throughput_kg_h": s["throughput_kg_h"],
        "mqtt_connected": s["mqtt_connected"],
        "sensors": s["sensors"],
        "motors": s["motors"],
        "controller_connected": False,
    })

@app.route("/status/simple", methods=["GET"])
def status_simple():
    """Simple one-line status for dashboards."""
    s = _state.get_all()
    return ok({
        "state": s["state"],
        "active": s["active"],
        "throughput_kg_h": s["throughput_kg_h"],
        "uptime_s": s["uptime_s"],
    })


# ============================================================
# Bins
# ============================================================

@app.route("/bins", methods=["GET"])
def get_bins():
    """Get fill levels for all 8 bins."""
    return ok(_state.get_bin_levels())

@app.route("/bins/<bin_id>", methods=["GET"])
def get_bin(bin_id):
    """Get fill level for specific bin."""
    if bin_id not in _VALID_BINS:
        return error(f"Unknown bin: {bin_id}", 404)
    level = _state.get_bin_levels().get(bin_id, 0.0)
    return ok({"bin_id": bin_id, "level_g": level, "capacity_g": 100.0})

@app.route("/bins/<bin_id>", methods=["PUT"])
@require_api_key
def set_bin(bin_id):
    """Manually set bin fill level (for testing/calibration)."""
    if bin_id not in _VALID_BINS:
        return error(f"Unknown bin: {bin_id}", 404)
    data = request.get_json() or {}
    level = data.get("level_g")
    if level is None:
        return error("level_g required")
    try:
        level = float(level)
        if level < 0:
            return error("level_g must be >= 0")
    except (TypeError, ValueError):
        return error("level_g must be a number")
    _state.set_bin_level(bin_id, level)
    return ok({"bin_id": bin_id, "level_g": level})


# ============================================================
# Batch
# ============================================================

@app.route("/batch/current", methods=["GET"])
def current_batch():
    """Get current batch statistics. P1-09: reads from real controller."""
    if _controller is not None:
        try:
            batch = _controller._current_batch
            if batch is None:
                return ok({"active": False, "batch": None})
            return ok({
                "active": True,
                "batch": {
                    "batch_id": batch.batch_id,
                    "timestamp": batch.timestamp,
                    "total_weight_kg": batch.total_weight_kg,
                    "feed_sequence": batch.feed_sequence,
                    "beans_count": len(batch.beans),
                },
            })
        except Exception as e:
            return ok({"error": f"Controller error: {e}"})
    s = _state.get_all()
    batch = s.get("current_batch")
    if not batch:
        return ok({"active": False, "batch": None})
    return ok({"active": True, "batch": batch})

@app.route("/batch/history", methods=["GET"])
def batch_history():
    """Get recent batch history."""
    # In production this reads from SQLite
    # For now, return mock structure
    return ok({
        "batches": [],
        "total_count": 0,
        "limit": request.args.get("limit", 10, type=int),
    })


# ============================================================
# Configuration
# ============================================================

@app.route("/config", methods=["GET"])
def get_config():
    """Get current configuration."""
    return ok(_state.get_config())

@app.route("/config", methods=["PUT", "PATCH"])
@require_api_key
def update_config():
    """Update configuration (partial or full)."""
    data = request.get_json() or {}
    if not data:
        return error("JSON body required")
    updated = _state.update_config(data)
    return ok({"config": updated})


# ============================================================
# Calibration
# ============================================================

@app.route("/calibration/weight", methods=["POST"])
@require_api_key
def calibrate_weight():
    """
    Trigger weight sensor calibration.
    Body: {"method": "two-point", "weight1_g": 200, "reading1": 1234, ...}
    """
    data = request.get_json() or {}
    method = data.get("method", "two-point")
    # In production this would call HX711 calibration routines
    return ok({
        "calibration_method": method,
        "status": "initiated",
        "note": "Run physical test protocol to complete calibration"
    })

@app.route("/calibration/color", methods=["POST"])
@require_api_key
def calibrate_color():
    """
    Trigger color sensor calibration with reference tiles.
    Body: {"reference_tile_id": "A1", "expected_L": 40.5, ...}
    """
    data = request.get_json() or {}
    tile_id = data.get("reference_tile_id")
    if not tile_id:
        return error("reference_tile_id required")
    return ok({
        "reference_tile_id": tile_id,
        "status": "initiated",
        "note": "Use color calibration card for physical verification"
    })

@app.route("/calibration/moisture", methods=["POST"])
@require_api_key
def calibrate_moisture():
    """
    Trigger moisture probe calibration.
    Body: {"reference_samples": [{"moisture_pct": 10.0, "reading_pf": 1.47}, ...]}
    """
    data = request.get_json() or {}
    samples = data.get("reference_samples", [])
    return ok({
        "samples_count": len(samples),
        "status": "initiated",
        "note": "Use烘干法 for ground truth reference"
    })

@app.route("/calibration/status", methods=["GET"])
def calibration_status():
    """Get calibration status for all sensors."""
    return ok({
        "load_cell": {"calibrated": False, "last_cal": None},
        "color_top": {"calibrated": False, "last_cal": None},
        "color_bottom": {"calibrated": False, "last_cal": None},
        "moisture": {"calibrated": False, "last_cal": None},
        "density": {"calibrated": False, "last_cal": None},
    })


# ============================================================
# Control
# ============================================================

@app.route("/control/start", methods=["POST"])
@require_api_key
def control_start():
    """Start the sorting process. P1-09: calls real controller."""
    if _controller is not None:
        try:
            from sorter.control.main import Event
            _controller.post_event(Event.START)
            return ok({"action": "start", "state": _controller._state.name})
        except Exception as e:
            return error(f"Controller error: {e}", 500)
    _state.update({"active": True, "state": "sorting"})
    return ok({"action": "start", "state": "sorting"})

@app.route("/control/stop", methods=["POST"])
@require_api_key
def control_stop():
    """Stop the sorting process. P1-09: calls real controller."""
    if _controller is not None:
        try:
            from sorter.control.main import Event
            _controller.post_event(Event.STOP)
            return ok({"action": "stop", "state": _controller._state.name})
        except Exception as e:
            return error(f"Controller error: {e}", 500)
    _state.update({"active": False, "state": "idle"})
    return ok({"action": "stop", "state": "idle"})

@app.route("/control/pause", methods=["POST"])
@require_api_key
def control_pause():
    """Pause the sorting process. P1-09: calls real controller."""
    if _controller is not None:
        try:
            from sorter.control.main import Event
            _controller.post_event(Event.PAUSE)
            return ok({"action": "pause", "state": _controller._state.name})
        except Exception as e:
            return error(f"Controller error: {e}", 500)
    _state.update({"state": "paused"})
    return ok({"action": "pause", "state": "paused"})

@app.route("/control/motor/<motor_name>", methods=["GET"])
def motor_status(motor_name):
    """Get motor status."""
    motor = _state.get_motor_state(motor_name)
    if not motor:
        return error(f"Unknown motor: {motor_name}", 404)
    return ok({motor_name: motor})

@app.route("/control/motor/<motor_name>", methods=["PUT"])
@require_api_key
def motor_control(motor_name):
    """
    Enable/disable or set RPM for a motor.
    Body: {"enabled": true, "rpm": 60}
    """
    if motor_name not in _VALID_MOTORS:
        return error(f"Unknown motor: {motor_name}", 404)
    data = request.get_json() or {}
    updates = {}
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            return error("enabled must be a boolean")
        updates[f"motors.{motor_name}.enabled"] = data["enabled"]
    if "rpm" in data:
        try:
            rpm = float(data["rpm"])
        except (TypeError, ValueError):
            return error("rpm must be a number")
        rpm_range = _MOTOR_RPM_RANGE.get(motor_name)
        if rpm_range and not (rpm_range[0] <= rpm <= rpm_range[1]):
            return error(f"rpm must be {rpm_range[0]}-{rpm_range[1]} for {motor_name}")
        updates[f"motors.{motor_name}.rpm"] = rpm
    _state.update(updates)
    return ok({motor_name: _state.get_motor_state(motor_name)})


# ============================================================
# MQTT Status
# ============================================================

@app.route("/mqtt/status", methods=["GET"])
def mqtt_status():
    """Get MQTT connection and message stats."""
    s = _state.get_all()
    return ok({
        "connected": s["mqtt_connected"],
        "msgs_sent": s["mqtt_msgs_sent"],
        "msgs_received": s["mqtt_msgs_received"],
        "broker": s["config"].get("mqtt_broker", "mqtt.local"),
    })

@app.route("/mqtt/publish", methods=["POST"])
@require_api_key
def mqtt_publish():
    """
    Manually publish MQTT message (for testing).
    Body: {"topic": "...", "payload": {...}}
    """
    data = request.get_json() or {}
    topic = data.get("topic")
    payload = data.get("payload")
    if not topic or payload is None:
        return error("topic and payload required")
    # In production this would call SorterMQTTClient.publish()
    return ok({
        "topic": topic,
        "published": True,
        "note": "In production, route via SorterMQTTClient"
    })


# ============================================================
# API Key Management
# ============================================================

@app.route("/api-keys", methods=["GET"])
@require_api_key
def list_api_keys():
    """List registered API keys (names only, never exposes hashes)."""
    return ok({"keys": get_api_keys_info()})


# ============================================================
# Error handlers
# ============================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"status": "error", "message": "Internal server error"}), 500


# ============================================================
# Main entry point
# ============================================================

def run_server(host="0.0.0.0", port=5000, debug=False):
    """Run the Flask API server."""
    init_api_keys()
    print(f"[API] Starting HUSKY-SORTER REST API on {host}:{port}")
    auth_mode = "enabled" if os.environ.get("SORTER_API_AUTH_REQUIRED", "true").lower() in ("1", "true", "yes") else "disabled"
    print(f"[API] Authentication: {auth_mode}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_server(debug=os.environ.get("DEBUG", "false").lower() == "true")