from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.evaluation import calculate_ml_metrics, calculate_system_metrics
from smart_city_security.iot_sim import AttackInjector, TrafficGenerator
from smart_city_security.ml_detection import FeatureBuilder, train_detector
from smart_city_security.network import NetworkShim
from smart_city_security.pqc import ClassicalBackend, PQCBackend, SecureChannel
from smart_city_security.schemas import DetectionResult, GroundTruth, SecureMessage, Telemetry
from smart_city_security.security.audit import AuditLog
from smart_city_security.security.device_registry import DeviceRegistry


@dataclass(slots=True)
class PipelineResult:
    detections: list[DetectionResult]
    labels: dict[str, GroundTruth]
    ml_metrics: Any
    system_metrics: Any
    feature_names: tuple[str, ...]
    security_backend: str
    network_preset: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "detections": [asdict(item) for item in self.detections],
            "labels": {key: asdict(value) for key, value in self.labels.items()},
            "ml_metrics": self.ml_metrics.to_dict(),
            "system_metrics": self.system_metrics.to_dict(),
            "feature_names": self.feature_names,
            "security_backend": self.security_backend,
            "network_preset": self.network_preset,
        }


class SecurityPipeline:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        seed = int(config.get("seed", 42))
        network = config["network"]
        self.network = NetworkShim(
            network["preset"], seed=seed, sleep=network.get("sleep", False)
        )
        security = config["security"]
        backend_name = security.get("backend", "classical")
        backend: ClassicalBackend | PQCBackend | None
        if backend_name == "classical":
            backend = ClassicalBackend()
        elif backend_name == "pqc":
            backend = PQCBackend()
        elif backend_name == "none":
            backend = None
        else:
            raise ValueError(f"Unknown security backend: {backend_name}")
        self.backend_name = backend.name if backend else "none"
        self.channel = (
            SecureChannel(
                backend,
                max_messages=security.get("session_max_messages", 50),
                max_age_seconds=security.get("session_max_age_seconds", 300),
                replay_tolerance_seconds=security.get(
                    "replay_tolerance_seconds", 30
                ),
            )
            if backend
            else None
        )
        self.seed = seed
        identity = config.get("identity", {})
        self.registry = DeviceRegistry() if identity.get("require_enrollment", False) else None
        self.audit = AuditLog(config.get("deployment", {}).get("audit_log")) if config.get("deployment", {}).get("audit_log") else None
        if self.channel:
            self.channel.registry = self.registry
            self.channel.audit = self.audit

    def _normal_training_features(self) -> np.ndarray:
        simulation = self.config["simulation"]
        count = int(simulation["devices"])
        per_device = max(10, int(simulation["messages_per_device"]) // 2)
        messages = TrafficGenerator(count, self.seed + 100).generate(per_device)
        twin = TrafficDigitalTwin(self.config["digital_twin"]["history_window"])
        builder = FeatureBuilder(self.config["ml"]["include_divergence"])
        pairs = [(message, twin.observe(message)) for message in messages]
        _ids, features = builder.build_many(pairs)
        return features

    def run(self) -> PipelineResult:
        started = time.perf_counter()
        simulation = self.config["simulation"]
        generator = TrafficGenerator(int(simulation["devices"]), self.seed)
        normal = generator.generate(int(simulation["messages_per_device"]))
        if self.registry:
            for device in generator.devices:
                if not self.registry.authorize(device.device_id):
                    self.registry.enroll(device.device_id, device.device_type)
        injector = AttackInjector(self.seed + 1)
        messages, labels = injector.inject(normal, float(simulation["attack_ratio"]))

        detector = train_detector(
            self.config["ml"]["model"],
            self._normal_training_features(),
            contamination=float(self.config["ml"]["contamination"]),
            seed=self.seed,
        )
        twin = TrafficDigitalTwin(self.config["digital_twin"]["history_window"])
        feature_builder = FeatureBuilder(self.config["ml"]["include_divergence"])

        delivered: list[tuple[Telemetry, np.ndarray]] = []
        rejected: dict[str, str] = {}
        cached_wire: dict[str, SecureMessage | Telemetry] = {}
        transport_sequence: dict[str, int] = {}
        latencies: list[float] = []
        wire_sizes: list[int] = []

        for candidate in messages:
            labels[candidate.message_id]
            transmission_started = time.perf_counter()
            source_id = injector.replay_sources.get(candidate.message_id)
            if self.channel and source_id:
                wire = cached_wire.get(source_id)
                if wire is None:
                    rejected[candidate.message_id] = "Replay source unavailable"
                    continue
            elif self.channel:
                next_sequence = transport_sequence.get(candidate.device_id, 0) + 1
                transport_sequence[candidate.device_id] = next_sequence
                secured = replace(candidate, sequence_number=next_sequence)
                try:
                    wire = self.channel.protect(secured)
                except ValueError as exc:
                    rejected[candidate.message_id] = str(exc)
                    continue
                cached_wire[candidate.message_id] = wire
            else:
                wire = candidate
                cached_wire[candidate.message_id] = wire

            serialized_size = len(wire.to_bytes()) if self.channel else len(candidate.to_bytes())
            transmission = self.network.transmit(wire)
            latencies.append(
                (time.perf_counter() - transmission_started) * 1000
                + transmission.delay_ms
            )
            wire_sizes.append(serialized_size)
            if not transmission.delivered:
                continue
            try:
                if self.channel:
                    if not isinstance(transmission.payload, SecureMessage):
                        rejected[candidate.message_id] = "Delivered payload was not a secure message"
                        continue
                    telemetry = self.channel.unprotect(transmission.payload)
                else:
                    if not isinstance(transmission.payload, Telemetry):
                        rejected[candidate.message_id] = "Delivered payload was not telemetry"
                        continue
                    telemetry = transmission.payload
            except ValueError as exc:
                rejected[candidate.message_id] = str(exc)
                continue
            state = twin.observe(telemetry)
            feature = feature_builder.build(telemetry, state).values
            delivered.append((candidate, feature))

        detections: list[DetectionResult] = []
        if delivered:
            matrix = np.vstack([feature for _message, feature in delivered])
            predictions, scores = detector.predict(matrix)
            for (original, _feature), prediction, score in zip(
                delivered, predictions, scores, strict=True
            ):
                detections.append(
                    DetectionResult(
                        original.message_id,
                        bool(prediction),
                        float(score),
                        detector.name,
                    )
                )
        for message_id, reason in rejected.items():
            detections.append(
                DetectionResult(
                    message_id,
                    True,
                    float("inf"),
                    "transport-security",
                    transport_rejected=True,
                    rejection_reason=reason,
                )
            )

        evaluated = [item for item in detections if item.message_id in labels]
        ml_metrics = calculate_ml_metrics(
            [labels[item.message_id].is_attack for item in evaluated],
            [item.is_anomaly for item in evaluated],
            [
                item.anomaly_score
                if np.isfinite(item.anomaly_score)
                else max(
                    (
                        candidate.anomaly_score
                        for candidate in evaluated
                        if np.isfinite(candidate.anomaly_score)
                    ),
                    default=1.0,
                )
                + 1.0
                for item in evaluated
            ],
        )
        elapsed = time.perf_counter() - started
        system_metrics = calculate_system_metrics(
            sent=len(messages),
            delivered=len(delivered),
            rejected=len(rejected),
            elapsed_seconds=elapsed,
            latencies_ms=latencies,
            wire_sizes=wire_sizes,
        )
        return PipelineResult(
            detections=detections,
            labels=labels,
            ml_metrics=ml_metrics,
            system_metrics=system_metrics,
            feature_names=feature_builder.feature_names,
            security_backend=self.backend_name,
            network_preset=self.network.preset.name,
        )
