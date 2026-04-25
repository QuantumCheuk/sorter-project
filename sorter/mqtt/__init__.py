"""
MQTT Client for HUSKY-SORTER-001
=================================
Manages MQTT communication between sorter and roaster.

Topics:
- sorter/{id}/batch/output     → batch ready (sorter publishes)
- sorter/{id}/batch/feed       → feed control (sorter publishes)
- sorter/{id}/status           → sorter status (sorter publishes)
- roaster/{id}/batch/input     → roaster requests beans (roaster publishes)
- roaster/{id}/status          → roaster status (roaster publishes)
- roaster/{id}/ready           → roaster ready to receive (roaster publishes)

Quality grades: A (≥70%), B (60-70%), C (<60% by operator config)

Author: Little Husky 🐕 | Date: 2026-04-26
"""

import json
import time
import threading
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from threading import Lock


# ---------------------------------------------------------------
# Dataclasses for batch data
# ---------------------------------------------------------------

class QualityGrade(Enum):
    A = "A"
    B = "B"
    C = "C"
    REJECT = "rejected"


@dataclass
class BatchStats:
    """Per-batch statistics sent to roaster."""
    batch_id: str
    total_beans: int
    grade_a_g: float
    grade_b_g: float
    grade_c_g: float
    rejected_g: float
    avg_weight_mg: float
    avg_density_g_cm3: float
    avg_moisture_pct: float
    variety: str = ""
    process: str = ""
    origin: str = ""

    def to_dict(self) -> Dict:
        return {**asdict(self), 'quality_grades': {}}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class FeedCommand:
    """Command from roaster requesting beans."""
    batch_id: str
    target_weight_g: float
    grade_preference: str  # "A", "B", "A+B", "any"
    variety: str = ""
    process: str = ""
    urgency: int = 1  # 1=normal, 5=urgent

    @classmethod
    def from_json(cls, data: str) -> 'FeedCommand':
        d = json.loads(data)
        return cls(**d)


@dataclass
class BatchFeedComplete:
    """Notification that batch feeding is complete."""
    batch_id: str
    actual_weight_g: float
    dispensed_bins: List[str]
    duration_s: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ---------------------------------------------------------------
# MQTT Topics
# ---------------------------------------------------------------

def make_sorter_topic(sorter_id: str, action: str) -> str:
    return f"sorter/{sorter_id}/{action}"


def make_roaster_topic(roaster_id: str, action: str) -> str:
    return f"roaster/{roaster_id}/{action}"


# ---------------------------------------------------------------
# MQTT Client
# ---------------------------------------------------------------

class SorterMQTTClient:
    """
    MQTT client managing sorter ↔ roaster communication.

    Handles:
    - Publishing batch-ready notifications
    - Subscribing to roaster feed requests
    - Publishing feed-complete acknowledgements
    - Heartbeat status publishing
    - Retain session across disconnections
    """

    # Default topics (can be overridden per instance)
    DEFAULT_SORTER_ID = "sorter-001"
    DEFAULT_ROASTER_ID = "roaster-001"

    QOS_AT_LEAST_ONCE = 1
    QOS_EXACTLY_ONCE = 2
    QOS_AT_MOST_ONCE = 0

    def __init__(
        self,
        sorter_id: str = None,
        roaster_id: str = None,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        username: str = None,
        password: str = None,
        client_id: str = None,
    ):
        self.sorter_id = sorter_id or self.DEFAULT_SORTER_ID
        self.roaster_id = roaster_id or self.DEFAULT_ROASTER_ID
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.client_id = client_id or f"sorter-{int(time.time())}"

        self._client = None
        self._connected = False
        self._lock = Lock()

        # Message handlers
        self._on_feed_request: Optional[Callable[[FeedCommand], None]] = None
        self._on_roaster_status: Optional[Callable[[Dict], None]] = None

        # Session state
        self._session_start = time.time()
        self._msgs_sent = 0
        self._msgs_received = 0
        self._last_feed_request: Optional[FeedCommand] = None
        self._upstream_ready = False

    # ---------------------------------------------------------------
    # Connection management
    # ---------------------------------------------------------------

    def _ensure_client(self):
        """Lazy-init paho client."""
        if self._client is not None:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise ImportError("paho-mqtt required: pip install paho-mqtt")

        self._client = mqtt.Client(
            client_id=self.client_id,
            protocol=mqtt.MQTTv311,
            clean_session=False,  # Retain session
        )

        if self.username and self.password:
            self._client.username_pw_set(self.username, self.password)

        # TLS options (for production)
        # self._client.tls_set()

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_publish = self._on_publish

    def connect(self, timeout_s: float = 10.0) -> bool:
        """Connect to MQTT broker. Returns True on success."""
        self._ensure_client()

        try:
            self._client.connect(
                self.broker_host,
                self.broker_port,
                keepalive=60,
            )
            self._client.loop_start()
            # Wait for connection
            start = time.time()
            while not self._connected and (time.time() - start) < timeout_s:
                time.sleep(0.1)
            return self._connected
        except Exception as e:
            print(f"[MQTT] Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from broker."""
        with self._lock:
            if self._client:
                self._client.loop_stop()
                self._client.disconnect()
                self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ---------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            print(f"[MQTT] Connected to {self.broker_host}:{self.broker_port}")
            self._subscribe_roaster_topics()
        else:
            print(f"[MQTT] Connection failed, rc={rc}")
            self._connected = False

    def _on_disconnect(self, client, userdata, rc):
        print(f"[MQTT] Disconnected, rc={rc}")
        self._connected = False
        if rc != 0:
            # Unexpected disconnect — attempt reconnect
            threading.Thread(target=self._reconnect, daemon=True).start()

    def _reconnect(self, delay_s: float = 5.0):
        """Auto-reconnect after delay."""
        time.sleep(delay_s)
        print("[MQTT] Attempting reconnect...")
        self.connect()

    def _on_message(self, client, userdata, msg):
        self._msgs_received += 1
        topic = msg.topic
        payload = msg.payload.decode('utf-8', errors='replace')

        try:
            if topic == make_roaster_topic(self.roaster_id, "batch/input"):
                cmd = FeedCommand.from_json(payload)
                self._last_feed_request = cmd
                if self._on_feed_request:
                    self._on_feed_request(cmd)

            elif topic == make_roaster_topic(self.roaster_id, "ready"):
                d = json.loads(payload)
                self._upstream_ready = d.get("ready", False)

            elif topic == make_roaster_topic(self.roaster_id, "status"):
                d = json.loads(payload)
                if self._on_roaster_status:
                    self._on_roaster_status(d)

        except json.JSONDecodeError:
            print(f"[MQTT] Malformed JSON on {topic}: {payload[:100]}")

    def _on_publish(self, client, userdata, mid):
        self._msgs_sent += 1

    def _subscribe_roaster_topics(self):
        """Subscribe to all roaster topics."""
        if not self._client:
            return
        t = self._roaster_topic
        self._client.subscribe(t("batch/input"), qos=1)
        self._client.subscribe(t("ready"), qos=1)
        self._client.subscribe(t("status"), qos=1)

    def _sorter_topic(self, action: str) -> str:
        return make_sorter_topic(self.sorter_id, action)

    def _roaster_topic(self, action: str) -> str:
        return make_roaster_topic(self.roaster_id, action)

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    def set_on_feed_request(self, handler: Callable[[FeedCommand], None]):
        """Register handler for roaster feed requests."""
        self._on_feed_request = handler

    def set_on_roaster_status(self, handler: Callable[[Dict], None]):
        """Register handler for roaster status updates."""
        self._on_roaster_status = handler

    def publish_batch_ready(self, batch: BatchStats) -> int:
        """
        Publish batch-ready notification to roaster.
        Returns msg_id on success, -1 on failure.
        """
        if not self._connected:
            return -1
        topic = self._sorter_topic("batch/output")
        payload = batch.to_json()
        result = self._client.publish(topic, payload, qos=self.QOS_AT_LEAST_ONCE, retain=True)
        return result.mid

    def publish_feed_complete(self, report: BatchFeedComplete) -> int:
        """Publish feed-complete notification."""
        if not self._connected:
            return -1
        topic = self._sorter_topic("batch/feed")
        result = self._client.publish(topic, report.to_json(), qos=self.QOS_EXACTLY_ONCE)
        return result.mid

    def publish_status(
        self,
        state: str,
        bins: Dict[str, float],
        throughput_kg_h: float = 0.0,
        active: bool = True,
    ) -> int:
        """Publish sorter status (call periodically, e.g. every 10s)."""
        if not self._connected:
            return -1
        topic = self._sorter_topic("status")
        payload = json.dumps({
            "timestamp": datetime.now().isoformat(),
            "state": state,
            "active": active,
            "upstream_ready": self._upstream_ready,
            "throughput_kg_h": round(throughput_kg_h, 3),
            "bins": {bid: round(level, 1) for bid, level in bins.items()},
            "msgs_sent": self._msgs_sent,
            "msgs_received": self._msgs_received,
            "uptime_s": round(time.time() - self._session_start, 1),
        }, ensure_ascii=False)
        result = self._client.publish(topic, payload, qos=self.QOS_AT_MOST_ONCE, retain=True)
        return result.mid

    def is_upstream_ready(self) -> bool:
        """Check if roaster is ready to receive beans."""
        return self._upstream_ready

    def get_last_feed_request(self) -> Optional[FeedCommand]:
        """Get most recent feed request from roaster."""
        return self._last_feed_request

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "connected": self._connected,
            "msgs_sent": self._msgs_sent,
            "msgs_received": self._msgs_received,
            "uptime_s": round(time.time() - self._session_start, 1),
            "last_feed_request": (
                asdict(self._last_feed_request)
                if self._last_feed_request else None
            ),
            "upstream_ready": self._upstream_ready,
        }


# ---------------------------------------------------------------
# Batch Dispatcher (integrates MQTT with BufferBinController)
# ---------------------------------------------------------------

class BatchDispatcher:
    """
    High-level batch dispatch coordinator.
    Bridges MQTT feed requests → BufferBinController dispensing.
    """

    def __init__(self, mqtt_client: SorterMQTTClient, buffer_controller):
        self.mqtt = mqtt_client
        self.buffer = buffer_controller
        self._active_batch_id: Optional[str] = None
        self._dispatch_history: List[Dict] = []
        self._lock = Lock()

        # Wire up MQTT handler
        self.mqtt.set_on_feed_request(self._handle_feed_request)

    def _handle_feed_request(self, cmd: FeedCommand):
        """Called when roaster sends a feed request."""
        print(f"[Dispatcher] Feed request: batch={cmd.batch_id}, "
              f"target={cmd.target_weight_g}g, grade={cmd.grade_preference}")

        start = time.time()
        success = self.buffer.dispense_to_roaster(
            bin_id=None,  # auto-select
            batch_weight_g=cmd.target_weight_g,
        )
        duration = time.time() - start

        if success:
            self._active_batch_id = cmd.batch_id
            report = BatchFeedComplete(
                batch_id=cmd.batch_id,
                actual_weight_g=cmd.target_weight_g,  # actual should come from buffer
                dispensed_bins=[],  # TODO: fill from buffer
                duration_s=round(duration, 2),
            )
            self.mqtt.publish_feed_complete(report)
            self._dispatch_history.append({
                "batch_id": cmd.batch_id,
                "success": True,
                "duration_s": duration,
            })
        else:
            self._dispatch_history.append({
                "batch_id": cmd.batch_id,
                "success": False,
                "duration_s": duration,
            })

    def get_dispatch_history(self) -> List[Dict]:
        return list(self._dispatch_history)


# ---------------------------------------------------------------
# CLI Sanity Test
# ---------------------------------------------------------------

if __name__ == '__main__':
    print("=== SorterMQTTClient Sanity Test ===\n")

    # 1. Dataclass roundtrips
    cmd = FeedCommand(
        batch_id="BATCH-001",
        target_weight_g=250.0,
        grade_preference="A+B",
        variety="Heirloom",
        process="Washed",
        urgency=2,
    )
    print(f"FeedCommand → JSON → FeedCommand:")
    restored = FeedCommand.from_json(cmd.to_json())
    print(f"  {restored}\n")

    # 2. BatchStats
    batch = BatchStats(
        batch_id="BATCH-001",
        total_beans=1250,
        grade_a_g=180.2,
        grade_b_g=45.5,
        grade_c_g=18.1,
        rejected_g=6.2,
        avg_weight_mg=147.2,
        avg_density_g_cm3=0.52,
        avg_moisture_pct=10.8,
        variety="Heirloom",
        process="Washed",
    )
    print(f"BatchStats JSON (truncated):\n{batch.to_json()[:200]}\n")

    # 3. MQTT client instantiation (no actual connection)
    client = SorterMQTTClient(
        sorter_id="sorter-001",
        roaster_id="roaster-001",
        broker_host="localhost",
    )
    print(f"MQTT Client created: client_id={client.client_id}")
    print(f"Topics:")
    print(f"  sorter/sorter-001/batch/output  (publish)")
    print(f"  sorter/sorter-001/batch/feed    (publish)")
    print(f"  sorter/sorter-001/status        (publish)")
    print(f"  roaster/roaster-001/batch/input (subscribe)")
    print(f"  roaster/roaster-001/ready       (subscribe)")
    print(f"  roaster/roaster-001/status      (subscribe)")

    print("\nNote: Actual MQTT connection requires broker + 'pip install paho-mqtt'")
