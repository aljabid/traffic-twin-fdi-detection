from __future__ import annotations

import bisect
import random
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

import numpy as np

from smart_city_security.ml_detection import AnomalyDetector, FeatureBuilder
from smart_city_security.schemas import GroundTruth, Telemetry, TwinState

_SPEED_MIN, _SPEED_MAX = 0.0, 89.0
_OCC_MIN, _OCC_MAX = 0.0, 1.0
_GRAD_STEPS = 8
_GRAD_EPS = 0.04
_GRAD_LR = 0.5
REPLAY_MIN_LAG_S = 300.0
TIME_SHIFT_MAX_S = 10.0
POSITION_SPOOF_MAX_M = 150.0
NOISE_SPEED_KMH = 25.0
NOISE_OCCUPANCY = 0.4


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class Attack:

    name: str
    speed_bias_kmh: float
    occupancy_bias: float
    kind: str = "bias"

    def apply(
        self,
        message: Telemetry,
        speed_strength: float,
        occupancy_strength: float,
        *,
        message_id: str,
        reference: Telemetry | None = None,
        progress: float = 1.0,
    ) -> Telemetry:
        ss = _clip(speed_strength, 0.0, 1.0)
        os_ = _clip(occupancy_strength, 0.0, 1.0)
        if self.kind == "backdate":
            return replace(message, message_id=message_id,
                           timestamp=message.timestamp - ss * TIME_SHIFT_MAX_S)
        if self.kind == "identity_spoof":
            if reference is None:
                raise ValueError("identity_spoof attack needs a reference device")
            device_id = reference.device_id if ss > 0.0 else message.device_id
            return replace(message, message_id=message_id, device_id=device_id)
        if self.kind == "noise_injection":
            u = (zlib.crc32(f"s:{message.message_id}".encode()) / 0xFFFFFFFF) * 2.0 - 1.0
            v = (zlib.crc32(f"o:{message.message_id}".encode()) / 0xFFFFFFFF) * 2.0 - 1.0
            return replace(
                message, message_id=message_id,
                speed=round(_clip(message.speed + ss * NOISE_SPEED_KMH * u, _SPEED_MIN, _SPEED_MAX), 4),
                occupancy=round(_clip(message.occupancy + os_ * NOISE_OCCUPANCY * v, _OCC_MIN, _OCC_MAX), 4),
            )
        if self.kind in ("time_shift", "position_spoof"):
            if self.kind == "time_shift":
                return replace(message, message_id=message_id,
                               timestamp=message.timestamp + ss * TIME_SHIFT_MAX_S)
            return replace(message, message_id=message_id,
                           position=round(message.position + ss * POSITION_SPOOF_MAX_M, 4))
        if self.kind == "coupled":
            speed = _clip(message.speed + self.speed_bias_kmh * ss, _SPEED_MIN, _SPEED_MAX)
            occupancy = 1.0 - speed / COUPLED_FREE_FLOW_KMH
            return replace(message, message_id=message_id, speed=round(speed, 4),
                           occupancy=round(_clip(occupancy, _OCC_MIN, _OCC_MAX), 4))
        if self.kind in ("replay", "stuck_at"):
            if reference is None:
                raise ValueError(f"{self.kind} attack needs a reference reading")
            speed = message.speed + ss * (reference.speed - message.speed)
            occupancy = message.occupancy + os_ * (reference.occupancy - message.occupancy)
        else:
            scale = _clip(progress, 0.0, 1.0) if self.kind == "drift" else 1.0
            speed = message.speed + self.speed_bias_kmh * ss * scale
            occupancy = message.occupancy + self.occupancy_bias * os_ * scale
        return replace(
            message,
            message_id=message_id,
            speed=round(_clip(speed, _SPEED_MIN, _SPEED_MAX), 4),
            occupancy=round(_clip(occupancy, _OCC_MIN, _OCC_MAX), 4),
        )


CONGESTION_SPOOF = Attack("congestion_spoof", speed_bias_kmh=-22.0, occupancy_bias=+0.45)
CLEAR_ROAD_SPOOF = Attack("clear_road_spoof", speed_bias_kmh=+18.0, occupancy_bias=-0.35)
DRIFT_CONGESTION = Attack("drift_congestion", speed_bias_kmh=-30.0, occupancy_bias=+0.6, kind="drift")
REPLAY_STALE = Attack("replay_stale", speed_bias_kmh=0.0, occupancy_bias=0.0, kind="replay")
STUCK_AT = Attack("stuck_at", speed_bias_kmh=0.0, occupancy_bias=0.0, kind="stuck_at")
TIME_SHIFT = Attack("time_shift", speed_bias_kmh=0.0, occupancy_bias=0.0, kind="time_shift")
POSITION_SPOOF = Attack("position_spoof", speed_bias_kmh=0.0, occupancy_bias=0.0, kind="position_spoof")
ATTACKS: dict[str, Attack] = {
    a.name: a for a in (CONGESTION_SPOOF, CLEAR_ROAD_SPOOF, DRIFT_CONGESTION, REPLAY_STALE,
                        STUCK_AT, TIME_SHIFT, POSITION_SPOOF)
}
IDENTITY_SPOOF = Attack("identity_spoof", speed_bias_kmh=0.0, occupancy_bias=0.0, kind="identity_spoof")
NOISE_INJECTION = Attack("noise_injection", speed_bias_kmh=0.0, occupancy_bias=0.0, kind="noise_injection")
BACKDATE = Attack("backdate", speed_bias_kmh=0.0, occupancy_bias=0.0, kind="backdate")
ATTACKS.update({a.name: a for a in (IDENTITY_SPOOF, NOISE_INJECTION, BACKDATE)})
NOVEL_ATTACKS = ("stuck_at", "time_shift", "position_spoof")
NOVEL_ATTACKS_2 = ("identity_spoof", "noise_injection", "backdate")
REHEARSAL_ATTACKS = ("congestion_spoof", "clear_road_spoof", "drift_congestion", "replay_stale")

COUPLED_FREE_FLOW_KMH = 50.0
CONGESTION_COUPLED = Attack("congestion_coupled", speed_bias_kmh=-22.0, occupancy_bias=0.0, kind="coupled")
CLEAR_ROAD_COUPLED = Attack("clear_road_coupled", speed_bias_kmh=+18.0, occupancy_bias=0.0, kind="coupled")
ATTACKS.update({a.name: a for a in (CONGESTION_COUPLED, CLEAR_ROAD_COUPLED)})
COUPLED_ATTACKS = ("congestion_coupled", "clear_road_coupled")


@dataclass(frozen=True, slots=True)
class CampaignResult:
    messages: list[Telemetry]
    labels: dict[str, GroundTruth]
    attacker_strength: float
    evaded_fraction: float
    mean_strength_used: float
    mean_speed_strength_used: float
    mean_occupancy_strength_used: float
    episodes: tuple[tuple[str, float, float], ...] = ()


class AdversarialCampaign:

    def __init__(self, seed: int = 42, *, search_steps: int = _GRAD_STEPS, search: str = "gradient") -> None:
        if search not in ("gradient", "grid"):
            raise ValueError("search must be 'gradient' or 'grid'")
        self.random = random.Random(seed)
        self.search_steps = search_steps
        self.search = search

    def _build_batch(
        self,
        attack: Attack,
        targets: Sequence[Telemetry],
        twin_states: Sequence[TwinState],
        points: np.ndarray,
        feature_builder: FeatureBuilder,
        contexts: Sequence[tuple[Telemetry | None, float]],
    ) -> np.ndarray:
        rows = []
        for target, twin_state, (ss, os_), (reference, progress) in zip(
            targets, twin_states, points, contexts, strict=True
        ):
            candidate = attack.apply(
                target, float(ss), float(os_), message_id="probe",
                reference=reference, progress=progress,
            )
            rows.append(feature_builder.build(candidate, twin_state, commit=False).values)
        return np.vstack(rows)

    def _contexts(
        self, attack: Attack, targets: Sequence[Telemetry], benign: Sequence[Telemetry]
    ) -> list[tuple[Telemetry | None, float]]:
        progress = [1.0] * len(targets)
        if attack.kind == "drift":
            order = sorted(range(len(targets)), key=lambda i: (targets[i].timestamp, targets[i].message_id))
            for rank, i in enumerate(order):
                progress[i] = (rank + 1) / len(targets)
        references: list[Telemetry | None] = [None] * len(targets)
        if attack.kind == "replay":
            by_time = sorted(benign, key=lambda m: (m.timestamp, m.message_id))
            times = [m.timestamp for m in by_time]
            earliest = by_time[: max(1, len(by_time) // 10)]
            for i, target in enumerate(targets):
                stale = bisect.bisect_right(times, target.timestamp - REPLAY_MIN_LAG_S)
                pool = by_time[:stale] or earliest
                references[i] = pool[self.random.randrange(len(pool))]
        if attack.kind == "identity_spoof":
            devices = sorted({m.device_id for m in benign})
            by_device: dict[str, Telemetry] = {}
            for m in benign:
                by_device.setdefault(m.device_id, m)
            for i, target in enumerate(targets):
                others = [d for d in devices if d != target.device_id]
                references[i] = by_device[others[self.random.randrange(len(others))]] if others else target
        if attack.kind == "stuck_at":
            first: dict[str, Telemetry] = {}
            for m in sorted(benign, key=lambda m: (m.timestamp, m.message_id)):
                first.setdefault(m.device_id, m)
            for i, target in enumerate(targets):
                references[i] = first.get(target.device_id, target)
        return list(zip(references, progress, strict=True))

    def _gradient_evasion(
        self,
        targets: Sequence[Telemetry],
        attack: Attack,
        detector: AnomalyDetector,
        feature_builder: FeatureBuilder,
        twin_states: Sequence[TwinState],
        base_strength: float,
        contexts: Sequence[tuple[Telemetry | None, float]],
    ) -> np.ndarray:
        n = len(targets)
        points = np.full((n, 2), base_strength, dtype=float)
        best_evading = np.zeros((n, 2), dtype=float)
        has_evaded = np.zeros(n, dtype=bool)

        for step in range(self.search_steps):
            base_feats = self._build_batch(attack, targets, twin_states, points, feature_builder, contexts)
            flags, scores = detector.predict(base_feats)
            flags = np.asarray(flags, dtype=bool)
            scores = np.asarray(scores, dtype=float)

            newly_evading = ~flags & ~has_evaded
            if newly_evading.any():
                best_evading[newly_evading] = points[newly_evading]
                has_evaded |= newly_evading
            still_searching = flags | (~has_evaded)
            if not still_searching.any():
                break

            can_back_s = points[:, 0] >= _GRAD_EPS
            probe_s = points.copy()
            probe_s[:, 0] = np.where(
                can_back_s, points[:, 0] - _GRAD_EPS,
                np.clip(points[:, 0] + _GRAD_EPS, 0.0, base_strength),
            )
            can_back_o = points[:, 1] >= _GRAD_EPS
            probe_o = points.copy()
            probe_o[:, 1] = np.where(
                can_back_o, points[:, 1] - _GRAD_EPS,
                np.clip(points[:, 1] + _GRAD_EPS, 0.0, base_strength),
            )
            _, scores_s = detector.predict(
                self._build_batch(attack, targets, twin_states, probe_s, feature_builder, contexts)
            )
            _, scores_o = detector.predict(
                self._build_batch(attack, targets, twin_states, probe_o, feature_builder, contexts)
            )
            sign_s = np.where(can_back_s, -1.0, 1.0)
            sign_o = np.where(can_back_o, -1.0, 1.0)
            grad_s = sign_s * (np.asarray(scores_s, dtype=float) - scores) / _GRAD_EPS
            grad_o = sign_o * (np.asarray(scores_o, dtype=float) - scores) / _GRAD_EPS
            norm = np.sqrt(grad_s**2 + grad_o**2) + 1e-9

            step_size = base_strength * _GRAD_LR * (0.6**step)
            active = flags.astype(float)
            points[:, 0] -= step_size * (grad_s / norm) * active
            points[:, 1] -= step_size * (grad_o / norm) * active
            points[:, 0] = np.clip(points[:, 0], 0.0, base_strength)
            points[:, 1] = np.clip(points[:, 1], 0.0, base_strength)

        final_feats = self._build_batch(attack, targets, twin_states, points, feature_builder, contexts)
        flags, _ = detector.predict(final_feats)
        flags = np.asarray(flags, dtype=bool)
        newly_evading = ~flags & ~has_evaded
        if newly_evading.any():
            best_evading[newly_evading] = points[newly_evading]
            has_evaded |= newly_evading

        result = np.where(has_evaded[:, None], best_evading, points)
        return result

    def _grid_evasion(
        self,
        targets: Sequence[Telemetry],
        attack: Attack,
        detector: AnomalyDetector,
        feature_builder: FeatureBuilder,
        twin_states: Sequence[TwinState],
        base_strength: float,
        contexts: Sequence[tuple[Telemetry | None, float]],
        levels: int = 7,
    ) -> np.ndarray:
        n = len(targets)
        grid = np.linspace(0.0, base_strength, levels)
        best = np.zeros((n, 2), dtype=float)
        best_norm = np.full(n, -1.0)
        lowest = np.full(n, np.inf)
        fallback = np.full((n, 2), base_strength, dtype=float)
        for ss in grid:
            for os_ in grid:
                points = np.tile([ss, os_], (n, 1))
                flags, scores = detector.predict(
                    self._build_batch(attack, targets, twin_states, points, feature_builder, contexts)
                )
                flags = np.asarray(flags, dtype=bool)
                scores = np.asarray(scores, dtype=float)
                norm = float(np.hypot(ss, os_))
                better = ~flags & (norm > best_norm)
                best[better] = (ss, os_)
                best_norm[better] = norm
                lower = scores < lowest
                fallback[lower] = (ss, os_)
                lowest[lower] = scores[lower]
        return np.where((best_norm >= 0.0)[:, None], best, fallback)

    def run(
        self,
        benign: Sequence[Telemetry],
        *,
        attack: Attack,
        attack_ratio: float = 0.15,
        strength: float = 0.6,
        adaptive: bool = False,
        detector: AnomalyDetector | None = None,
        feature_builder: FeatureBuilder | None = None,
        predict_twin_state: Callable[[Telemetry], TwinState] | None = None,
        mode: str = "inject",
        schedule: str = "random",
        episode_count: int = 20,
        episode_seconds: float = 30.0,
    ) -> CampaignResult:
        if mode not in ("inject", "replace"):
            raise ValueError("mode must be 'inject' or 'replace'")
        if schedule not in ("random", "episodes"):
            raise ValueError("schedule must be 'random' or 'episodes'")
        if not 0.0 <= attack_ratio <= 1.0:
            raise ValueError("attack_ratio must be in [0, 1]")
        adaptive_deps: tuple[AnomalyDetector, FeatureBuilder, Callable[[Telemetry], TwinState]] | None = None
        if adaptive:
            if detector is None or feature_builder is None or predict_twin_state is None:
                raise ValueError("adaptive mode needs detector, feature_builder and predict_twin_state")
            adaptive_deps = (detector, feature_builder, predict_twin_state)

        messages = list(benign)
        labels = {m.message_id: GroundTruth(m.message_id, "normal") for m in messages}
        episodes: tuple[tuple[str, float, float], ...] = ()
        if schedule == "episodes":
            targets, episodes = self._episode_targets(messages, episode_count, episode_seconds)
            n_attacks = len(targets)
        else:
            n_attacks = min(len(messages), round(len(messages) * attack_ratio))
            targets = self.random.sample(list(messages), n_attacks)
        contexts = self._contexts(attack, targets, benign)

        if adaptive_deps is not None and targets:
            active_detector, active_builder, active_predict = adaptive_deps
            twin_states = [active_predict(t) for t in targets]
            evasion = self._grid_evasion if self.search == "grid" else self._gradient_evasion
            points = evasion(
                targets, attack, active_detector, active_builder, twin_states, strength, contexts
            )
        else:
            points = np.full((len(targets), 2), strength, dtype=float)

        evaded = 0
        replaced: dict[str, Telemetry] = {}
        for original, (ss, os_), (reference, progress) in zip(targets, points, contexts, strict=True):
            message_id = original.message_id if mode == "replace" else f"adv-{original.message_id}"
            malicious = attack.apply(
                original, float(ss), float(os_), message_id=message_id,
                reference=reference, progress=progress,
            )
            if mode == "replace":
                replaced[original.message_id] = malicious
            else:
                messages.append(malicious)
            labels[malicious.message_id] = GroundTruth(malicious.message_id, "attack", attack.name)
            if adaptive and (ss < strength or os_ < strength):
                evaded += 1

        if replaced:
            messages = [replaced.get(m.message_id, m) for m in messages]
        messages.sort(key=lambda m: (m.timestamp, m.message_id))
        mean_s = float(np.mean(points[:, 0])) if len(points) else 0.0
        mean_o = float(np.mean(points[:, 1])) if len(points) else 0.0
        return CampaignResult(
            messages=messages,
            labels=labels,
            attacker_strength=strength,
            evaded_fraction=(evaded / n_attacks if n_attacks else 0.0),
            mean_strength_used=(mean_s + mean_o) / 2,
            mean_speed_strength_used=mean_s,
            mean_occupancy_strength_used=mean_o,
            episodes=episodes,
        )

    def _episode_targets(
        self, messages: Sequence[Telemetry], count: int, seconds: float
    ) -> tuple[list[Telemetry], tuple[tuple[str, float, float], ...]]:
        by_device: dict[str, list[Telemetry]] = {}
        for m in sorted(messages, key=lambda m: (m.timestamp, m.message_id)):
            by_device.setdefault(m.device_id, []).append(m)
        eligible = sorted(d for d, ms in by_device.items() if ms[-1].timestamp - ms[0].timestamp >= seconds)
        chosen = self.random.sample(eligible, min(count, len(eligible)))
        targets: list[Telemetry] = []
        episodes = []
        for device in chosen:
            ms = by_device[device]
            start = self.random.uniform(ms[0].timestamp, ms[-1].timestamp - seconds)
            window = [m for m in ms if start <= m.timestamp <= start + seconds]
            if window:
                targets.extend(window)
                episodes.append((device, start, start + seconds))
        return targets, tuple(episodes)
