from __future__ import annotations

import argparse
import base64
import json
import logging
import signal
import threading
from typing import Any

from smart_city_security.config import load_config
from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.ml_detection import (
    AnomalyDetector,
    DetectorCalibrator,
    FeatureBuilder,
    train_detector,
)
from smart_city_security.ml_detection.calibration import DEFAULT_CONTAMINATION_GRID
from smart_city_security.ml_detection.registry import ModelRegistry
from smart_city_security.ml_detection.train import load_detector

_LOG = logging.getLogger(__name__)
from smart_city_security.network import InMemoryMQTTClient, MQTTClient
from smart_city_security.network.mqtt_client import MQTTTLSConfig
from smart_city_security.observability import MetricsRegistry, Tracer, configure_logging
from smart_city_security.pqc import (
    ClassicalBackend,
    DeviceKey,
    PQCBackend,
    PreSharedKeyChannel,
    SecureChannel,
)
from smart_city_security.resilience.retry import RetryPolicy
from smart_city_security.schemas import SecureMessage, Telemetry
from smart_city_security.security.audit import AuditLog
from smart_city_security.security.device_registry import DeviceRegistry
from smart_city_security.services import (
    AlertStore,
    TelemetryIngestionService,
    TelemetryQualityPolicy,
)
from smart_city_security.services.health import HealthService
from smart_city_security.storage import InMemoryTelemetryRepository


def _assert_advisory_only(config: dict[str, Any]) -> None:
    operation = config.get("operation", {})
    if operation.get("automatic_control"):
        raise ValueError(
            "Refusing to start: operation.automatic_control is not permitted. "
            "v1 is advisory-only with no actuator command contract (see docs/safety_case.md)."
        )


def _build_channel(
    config: dict[str, Any], registry: DeviceRegistry | None, audit: AuditLog | None
) -> SecureChannel | PreSharedKeyChannel | None:
    security = config["security"]
    backend_name = security.get("backend", "classical")
    if backend_name == "none":
        return None
    if backend_name == "preshared":
        keys = [
            DeviceKey(
                entry["device_id"],
                base64.b64decode(entry["aes_key_b64"]),
                entry["public_key_pem"].encode(),
            )
            for entry in security.get("preshared_keys", [])
        ]
        return PreSharedKeyChannel(
            keys,
            replay_tolerance_seconds=security.get("replay_tolerance_seconds", 30),
            audit=audit,
        )
    backend = ClassicalBackend() if backend_name == "classical" else PQCBackend()
    return SecureChannel(
        backend,
        max_messages=security.get("session_max_messages", 50),
        max_age_seconds=security.get("session_max_age_seconds", 300),
        replay_tolerance_seconds=security.get("replay_tolerance_seconds", 30),
        registry=registry,
        audit=audit,
    )


def _bootstrap_detector(config: dict[str, Any]) -> AnomalyDetector:
    simulation = config["simulation"]
    ml = config["ml"]
    twin_window = config["digital_twin"]["history_window"]
    generator = TrafficGenerator(int(simulation["devices"]), int(config.get("seed", 42)))
    twin = TrafficDigitalTwin(twin_window)
    builder = FeatureBuilder(ml.get("include_divergence", True))
    per_device = max(10, int(simulation["messages_per_device"]))
    pairs = [(message, twin.observe(message)) for message in generator.generate(per_device)]
    _ids, features = builder.build_many(pairs)
    return train_detector(
        ml["model"], features,
        contamination=float(ml.get("contamination", 0.15)),
        seed=int(config.get("seed", 42)),
    )


def _load_or_bootstrap_detector(config: dict[str, Any]) -> AnomalyDetector:
    registry_path = config.get("deployment", {}).get(
        "model_registry", "results/models/registry.json"
    )
    registry = ModelRegistry(registry_path)
    record = registry.production(config["ml"]["model"])
    if record is not None:
        return load_detector(record.artifact)
    return _bootstrap_detector(config)


def _build_calibrator(config: dict[str, Any]) -> tuple[DetectorCalibrator | None, int]:
    calibration = config["ml"].get("calibration", {})
    if not calibration.get("enabled", False):
        return None, 0
    warmup_messages = int(calibration.get("warmup_messages", 200))
    if warmup_messages < 4:
        raise ValueError("ml.calibration.warmup_messages must be at least 4")
    grid = calibration.get("contamination_grid") or DEFAULT_CONTAMINATION_GRID
    calibrator = DetectorCalibrator(
        config["ml"]["model"],
        target_false_positive_rate=float(calibration.get("target_false_positive_rate", 0.05)),
        contamination_grid=tuple(grid),
        seed=int(config.get("seed", 42)),
    )
    return calibrator, warmup_messages


def _build_mqtt_client(config: dict[str, Any]) -> MQTTClient | InMemoryMQTTClient:
    network = config["network"]
    if network.get("mode") != "mqtt":
        return InMemoryMQTTClient()
    tls_config = network.get("tls")
    tls = (
        MQTTTLSConfig(tls_config["ca_file"], tls_config["certificate_file"], tls_config["private_key_file"])
        if tls_config
        else None
    )
    return MQTTClient(
        network["broker"],
        int(network.get("port", 8883)),
        client_id=config.get("deployment", {}).get("service_name", "smart-city-ingest"),
        tls=tls,
    )


class LiveIngestionDaemon:

    def __init__(self, config: dict[str, Any]):
        _assert_advisory_only(config)
        self.config = config
        self.topic = config["network"].get("topic", "smart-city/telemetry")

        self.audit = AuditLog(config.get("deployment", {}).get("audit_log"))
        self.metrics = MetricsRegistry()
        self.tracer = Tracer()
        self.alert_store = AlertStore()
        self.registry = (
            DeviceRegistry() if config.get("identity", {}).get("require_enrollment", False) else None
        )
        self.channel = _build_channel(config, self.registry, self.audit)
        self.repository = InMemoryTelemetryRepository()
        self.twin = TrafficDigitalTwin(config["digital_twin"]["history_window"])
        self.quality_policy = TelemetryQualityPolicy()
        self.feature_builder = FeatureBuilder(config["ml"].get("include_divergence", True))

        self.calibrator, self._warmup_messages = _build_calibrator(config)
        self._calibrating = self.calibrator is not None
        initial_detector = None if self._calibrating else _load_or_bootstrap_detector(config)

        self.ingestion_service = TelemetryIngestionService(
            self.repository,
            self.twin,
            channel=None,
            audit=self.audit,
            quality_policy=self.quality_policy,
            detector=initial_detector,
            feature_builder=self.feature_builder,
            alert_store=self.alert_store,
            metrics=self.metrics,
            tracer=self.tracer,
        )
        self.mqtt_client = _build_mqtt_client(config)
        self.health = HealthService(config.get("deployment", {}).get("service_name", "smart-city-ingest"))
        self.health.register("mqtt", lambda: self._connected)
        self.health.register("detector_calibrated", lambda: not self._calibrating)
        self._connected = False

    def _decode(self, payload: bytes) -> Telemetry | None:
        try:
            if self.channel:
                return self.channel.unprotect(SecureMessage.from_bytes(payload))
            return Telemetry.from_bytes(payload)
        except (ValueError, KeyError, TypeError) as exc:
            self.metrics.increment("telemetry_undecodable_total")
            if self.audit:
                self.audit.record("telemetry_undecodable", None, "failure", str(exc))
            return None

    def _collect_warmup(self, telemetry: Telemetry) -> None:
        calibrator = self.calibrator
        if calibrator is None:
            return
        quality = self.quality_policy.assess(telemetry)
        if not quality.accepted:
            self.metrics.increment("warmup_rejected_quality_total")
            return
        predicted = self.twin.predict(telemetry)
        calibrator.add(self.feature_builder.build(telemetry, predicted).values)
        self.twin.commit(telemetry)
        self.repository.append(telemetry)
        self.metrics.increment("warmup_samples_total")
        if calibrator.ready(self._warmup_messages):
            self._finish_calibration()

    def _finish_calibration(self) -> None:
        calibrator = self.calibrator
        if calibrator is None:
            return
        detector, result = calibrator.fit()
        self.ingestion_service.detector = detector
        self._calibrating = False
        self.calibrator = None
        _LOG.info("detector calibrated: %s", json.dumps(result.to_dict()))
        if self.audit:
            self.audit.record(
                "detector_calibrated",
                None,
                "success" if result.budget_met else "warning",
                json.dumps(result.to_dict()),
            )

    def _on_message(self, payload: bytes) -> None:
        telemetry = self._decode(payload)
        if telemetry is None:
            return
        try:
            if self._calibrating:
                self._collect_warmup(telemetry)
            else:
                self.ingestion_service.ingest(telemetry)
        except Exception as exc:
            self.metrics.increment("telemetry_ingest_error_total")
            if self.audit:
                self.audit.record("telemetry_ingest_error", None, "failure", str(exc))

    def start(self) -> None:
        RetryPolicy(attempts=5, base_delay_seconds=0.5, max_delay_seconds=5).execute(
            self.mqtt_client.connect
        )
        self._connected = True
        self.mqtt_client.subscribe(self.topic, self._on_message)

    def stop(self) -> None:
        self._connected = False
        self.mqtt_client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/development.yaml")
    args = parser.parse_args(argv)

    configure_logging()
    config = load_config(args.config)
    daemon = LiveIngestionDaemon(config)
    daemon.start()

    stop_event = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_args: stop_event.set())
    stop_event.wait()
    daemon.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
