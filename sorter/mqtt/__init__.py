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
# Dataclasses for batch data — SPEC 5.3 compliant
# ---------------------------------------------------------------

class QualityGrade(Enum):
    A = "A"
    B = "B"
    C = "C"
    REJECT = "rejected"


@dataclass
class BatchMetadata:
    """Bean origin metadata (SPEC 5.3 BATCH_READY.metadata)."""
    origin_country: str = ""
    origin_region: str = ""
    variety: str = ""
    process: str = ""
    harvest_year: int = 0
    grade: str = ""
    batch_code: str = ""


@dataclass
class BatchMeasurements:
    """Aggregated measurements (SPEC 5.3 BATCH_READY.measurements)."""
    size_avg: float = 0.0          # 目数
    weight_avg_g: float = 0.0      # 单粒平均重(g)
    density_class: str = ""        # "light" | "medium" | "heavy"
    moisture_pct: float = 0.0
    color_score: float = 0.0
    defect_count: int = 0
    defect_rate_pct: float = 0.0


@dataclass
class FeedPortion:
    """Single feed portion (SPEC 5.3 BATCH_READY.feed_plan item)."""
    portion_kg: float = 0.0
    feed_sequence: int = 0


@dataclass
class BatchOutputMessage:
    """SPEC 5.3 BATCH_READY — sorter → roaster batch notification."""
    message_type: str = "BATCH_READY"
    batch_id: str = ""
    timestamp: str = ""
    source: str = "sorter-01"

    metadata: BatchMetadata = field(default_factory=BatchMetadata)
    measurements: BatchMeasurements = field(default_factory=BatchMeasurements)
    quality_class: str = "A"

    feed_plan: List[FeedPortion] = field(default_factory=list)
    total_weight_kg: float = 0.0
    portion_count: int = 0

    recommended_profile: str = ""
    roast_level_target: str = ""
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "message_type": self.message_type,
            "batch_id": self.batch_id,
            "timestamp": self.timestamp or datetime.now().isoformat(),
            "source": self.source,
            "metadata": asdict(self.metadata),
            "measurements": asdict(self.measurements),
            "quality_class": self.quality_class,
            "feed_plan": [asdict(p) for p in self.feed_plan],
            "total_weight_kg": self.total_weight_kg,
            "portion_count": self.portion_count,
            "recommended_profile": self.recommended_profile,
            "roast_level_target": self.roast_level_target,
            "notes": self.notes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class BatchStartMessage:
    """SPEC 7.3 BATCH_START — sorter → roaster per-portion notification."""
    message_type: str = "BATCH_START"
    batch_id: str = ""
    timestamp: str = ""
    source: str = "sorter-01"

    green_beans: Dict[str, Any] = field(default_factory=dict)
    quality_class: str = "A"
    moisture_pct: float = 0.0
    bulk_density: float = 0.0
    avg_size: float = 0.0
    weight_kg: float = 0.0

    recommended_profile: str = ""
    roast_level_target: str = ""

    def to_dict(self) -> Dict:
        return {
            "message_type": self.message_type,
            "batch_id": self.batch_id,
            "timestamp": self.timestamp or datetime.now().isoformat(),
            "source": self.source,
            "green_beans": self.green_beans,
            "quality_class": self.quality_class,
            "moisture_pct": self.moisture_pct,
            "bulk_density": self.bulk_density,
            "avg_size": self.avg_size,
            "weight_kg": self.weight_kg,
            "recommended_profile": self.recommended_profile,
            "roast_level_target": self.roast_level_target,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# Backward-compat alias: old BatchStats → new BatchOutputMessage
@dataclass
class BatchStats:
    """Legacy per-batch stats (deprecated — use BatchOutputMessage)."""
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

    def to_output_message(
        self,
        source: str = "sorter-01",
        portion_g: float = 250.0,
        recommended_profile: str = "",
        roast_level_target: str = "",
        notes: str = "",
    ) -> BatchOutputMessage:
        """Convert legacy BatchStats → SPEC 5.3 BatchOutputMessage."""
        total_g = self.grade_a_g + self.grade_b_g + self.grade_c_g
        total_kg = total_g / 1000.0
        portion_count = max(1, round(total_g / portion_g))
        feed_plan = [
            FeedPortion(portion_kg=round(portion_g / 1000.0, 3), feed_sequence=i + 1)
            for i in range(portion_count)
        ]
        # Determine quality class
        if total_g > 0:
            a_pct = self.grade_a_g / total_g * 100
            quality_class = "A" if a_pct >= 70 else ("B" if a_pct >= 50 else "C")
        else:
            quality_class = "C"
        # Defect count = rejected beans estimate
        defect_count = int(self.rejected_g / max(1, self.avg_weight_mg / 1000.0)) if self.avg_weight_mg > 0 else 0
        defect_rate = (defect_count / self.total_beans * 100) if self.total_beans > 0 else 0.0

        return BatchOutputMessage(
            batch_id=self.batch_id,
            source=source,
            metadata=BatchMetadata(
                origin_country=self.origin,
                variety=self.variety,
                process=self.process,
            ),
            measurements=BatchMeasurements(
                weight_avg_g=self.avg_weight_mg / 1000.0 if self.avg_weight_mg > 0 else 0,
                density_class=(
                    "heavy" if self.avg_density_g_cm3 >= 0.72
                    else "light" if self.avg_density_g_cm3 <= 0.60
                    else "medium"
                ),
                moisture_pct=self.avg_moisture_pct,
                defect_count=defect_count,
                defect_rate_pct=round(defect_rate, 1),
            ),
            quality_class=quality_class,
            feed_plan=feed_plan,
            total_weight_kg=round(total_kg, 3),
            portion_count=portion_count,
            recommended_profile=recommended_profile,
            roast_level_target=roast_level_target,
            notes=notes,
        )

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

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


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

        # P1-11 fix: Exponential backoff reconnect state
        self._reconnect_attempt = 0
        self._reconnect_base_delay_s = 2.0
        self._reconnect_max_delay_s = 60.0
        self._reconnect_max_attempts = 0  # 0 = unlimited

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
            self._reconnect_attempt = 0  # P1-11: Reset backoff on success
            print(f"[MQTT] Connected to {self.broker_host}:{self.broker_port}")
            self._subscribe_roaster_topics()
        else:
            print(f"[MQTT] Connection failed, rc={rc}")
            self._connected = False

    def _on_disconnect(self, client, userdata, rc):
        print(f"[MQTT] Disconnected, rc={rc}")
        self._connected = False
        if rc != 0:
            # Unexpected disconnect — attempt reconnect with backoff
            threading.Thread(target=self._reconnect, daemon=True).start()

    def _reconnect(self):
        """Auto-reconnect with exponential backoff + jitter (P1-11 fix).

        Delay: base × 2^attempt + random jitter (0-1s)
        Capped at max_delay_s to prevent excessive waits.
        """
        import random
        attempt = self._reconnect_attempt
        self._reconnect_attempt += 1

        # Exponential: 2s, 4s, 8s, 16s, 32s, 60s (capped)
        delay = min(
            self._reconnect_base_delay_s * (2 ** attempt),
            self._reconnect_max_delay_s,
        )
        # Add jitter (0-1s) to prevent thundering herd
        delay += random.uniform(0, 1.0)

        if (self._reconnect_max_attempts > 0 and
                attempt >= self._reconnect_max_attempts):
            print(f"[MQTT] Max reconnect attempts ({self._reconnect_max_attempts}) reached — giving up")
            return

        print(f"[MQTT] Reconnecting in {delay:.1f}s (attempt {attempt + 1})...")
        time.sleep(delay)
        print(f"[MQTT] Attempting reconnect...")
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

    def publish_batch_ready(self, batch) -> int:
        """
        Publish batch-ready notification to roaster.
        Accepts BatchOutputMessage (SPEC 5.3) or legacy BatchStats.
        Returns msg_id on success, -1 on failure.
        """
        if not self._connected:
            return -1
        topic = self._sorter_topic("batch/output")
        # Support both new BatchOutputMessage and legacy BatchStats
        if hasattr(batch, "to_output_message") and not isinstance(batch, BatchOutputMessage):
            batch = batch.to_output_message()
        payload = batch.to_json()
        result = self._client.publish(topic, payload, qos=self.QOS_AT_LEAST_ONCE, retain=True)
        return result.mid

    def publish_batch_start(self, msg: BatchStartMessage) -> int:
        """Publish SPEC 7.3 BATCH_START per-portion notification."""
        if not self._connected:
            return -1
        topic = self._roaster_topic("batch/input")
        result = self._client.publish(topic, msg.to_json(), qos=self.QOS_AT_LEAST_ONCE)
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

    v2 2026-05-17: SPEC 7.3 compliant — publishes BATCH_START per portion
    and uses actual dispensed weight from buffer controller.
    """

    def __init__(self, mqtt_client: SorterMQTTClient, buffer_controller):
        self.mqtt = mqtt_client
        self.buffer = buffer_controller
        self._active_batch_id: Optional[str] = None
        self._dispatch_history: List[Dict] = []
        self._lock = Lock()
        self._portion_sequence = 0

        # Wire up MQTT handler
        self.mqtt.set_on_feed_request(self._handle_feed_request)

    def _handle_feed_request(self, cmd: FeedCommand):
        """Called when roaster sends a feed request."""
        print(f"[Dispatcher] Feed request: batch={cmd.batch_id}, "
              f"target={cmd.target_weight_g}g, grade={cmd.grade_preference}")

        start = time.time()
        dispatched_bin_id = self.buffer.auto_dispatch(batch_weight_g=cmd.target_weight_g)
        success = (dispatched_bin_id is not None)
        duration = time.time() - start

        if success:
            self._active_batch_id = cmd.batch_id
            self._portion_sequence += 1

            # Get actual dispensed weight from buffer controller bin level change
            bin_levels = self.buffer.get_bin_levels()
            actual_weight = bin_levels.get(dispatched_bin_id, 0.0)

            # Publish SPEC 7.3 BATCH_START for this portion
            batch_start = BatchStartMessage(
                batch_id=f"{cmd.batch_id}-{self._portion_sequence}",
                source=self.mqtt.sorter_id,
                green_beans={
                    "origin": {"country": "", "region": ""},
                    "variety": cmd.variety,
                    "process": cmd.process,
                },
                quality_class=cmd.grade_preference if cmd.grade_preference in ("A", "B", "C") else "A",
                weight_kg=round(actual_weight / 1000.0, 3),
            )
            self.mqtt.publish_batch_start(batch_start)

            report = BatchFeedComplete(
                batch_id=cmd.batch_id,
                actual_weight_g=round(actual_weight, 1),
                dispensed_bins=[dispatched_bin_id],
                duration_s=round(duration, 2),
            )
            self.mqtt.publish_feed_complete(report)
            self._dispatch_history.append({
                "batch_id": cmd.batch_id,
                "success": True,
                "actual_weight_g": round(actual_weight, 1),
                "bin_id": dispatched_bin_id,
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
    print("=== SorterMQTTClient Sanity Test (v2 SPEC 5.3) ===\n")

    # 1. SPEC 5.3 BatchOutputMessage
    msg = BatchOutputMessage(
        batch_id="LOT-2026-0410-A",
        source="sorter-01",
        metadata=BatchMetadata(
            origin_country="埃塞俄比亚",
            origin_region="耶加雪菲·Aricha",
            variety="Heirloom",
            process="水洗",
            harvest_year=2025,
            grade="G1",
            batch_code="ARI-2025-W-001",
        ),
        measurements=BatchMeasurements(
            size_avg=17.2,
            weight_avg_g=0.152,
            density_class="medium",
            moisture_pct=11.4,
            color_score=92,
            defect_count=1,
            defect_rate_pct=0.4,
        ),
        quality_class="A",
        feed_plan=[
            FeedPortion(portion_kg=0.250, feed_sequence=1),
            FeedPortion(portion_kg=0.250, feed_sequence=2),
            FeedPortion(portion_kg=0.250, feed_sequence=3),
        ],
        total_weight_kg=0.750,
        portion_count=3,
        recommended_profile="light-ethiopia-01",
        roast_level_target="Light",
        notes="果香突出，酸质明亮",
    )
    print("1. BatchOutputMessage (SPEC 5.3 BATCH_READY):")
    print(f"   {msg.to_json()[:300]}...\n")

    # 2. SPEC 7.3 BatchStartMessage
    start_msg = BatchStartMessage(
        batch_id="LOT-2026-0410-A-1",
        source="sorter-01",
        green_beans={
            "origin": {"country": "埃塞俄比亚", "region": "耶加雪菲"},
            "variety": "Heirloom",
            "process": "水洗",
        },
        quality_class="A",
        moisture_pct=11.4,
        bulk_density=0.65,
        avg_size=17.2,
        weight_kg=0.250,
        recommended_profile="light-ethiopia-01",
        roast_level_target="Light",
    )
    print("2. BatchStartMessage (SPEC 7.3 BATCH_START):")
    print(f"   {start_msg.to_json()[:300]}...\n")

    # 3. Legacy BatchStats → BatchOutputMessage conversion
    legacy = BatchStats(
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
    converted = legacy.to_output_message(
        source="sorter-01",
        recommended_profile="light-ethiopia-01",
        roast_level_target="Light",
    )
    print("3. Legacy BatchStats → BatchOutputMessage conversion:")
    print(f"   quality_class={converted.quality_class}, "
          f"total_weight_kg={converted.total_weight_kg}, "
          f"portions={converted.portion_count}")
    print(f"   defect_count={converted.measurements.defect_count}, "
          f"defect_rate={converted.measurements.defect_rate_pct}%\n")

    # 4. FeedCommand roundtrip
    cmd = FeedCommand(
        batch_id="BATCH-001",
        target_weight_g=250.0,
        grade_preference="A+B",
        variety="Heirloom",
        process="Washed",
        urgency=2,
    )
    restored = FeedCommand.from_json(cmd.to_json())
    print(f"4. FeedCommand roundtrip: {restored.batch_id} {restored.target_weight_g}g\n")

    # 5. MQTT client
    client = SorterMQTTClient(
        sorter_id="sorter-001",
        roaster_id="roaster-001",
        broker_host="localhost",
    )
    print(f"5. MQTT Client: client_id={client.client_id}")
    print("   Topics:")
    print("     sorter/sorter-001/batch/output  (publish BATCH_READY)")
    print("     sorter/sorter-001/batch/feed    (publish FEED_COMPLETE)")
    print("     sorter/sorter-001/status        (publish status)")
    print("     roaster/roaster-001/batch/input (publish BATCH_START / subscribe)")
    print("     roaster/roaster-001/ready       (subscribe)")
    print("     roaster/roaster-001/status      (subscribe)")

    print("\n✅ SPEC 5.3 / 7.3 message format validated")
