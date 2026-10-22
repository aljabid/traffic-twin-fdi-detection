# Experiment 6: Adversarially-Validated Divergence Selection (AVDS)

## Why this experiment exists

Experiment 5 (docs/experiment5_real_data.md) established that the
twin-divergence features have no fixed sign. They significantly help
Isolation Forest on SUMO, hurt LOF on SUMO and pNEUMA but help it on NGSIM,
and rescue the Mahalanobis detector from collapse under adaptive attack on
SUMO while doing nothing measurable for it on NGSIM or pNEUMA. That is a
finding about the feature, but it leaves a deployer with no rule: "always
include divergence" and "never include it" are each wrong somewhere.

This experiment turns the finding into a method and tests it. The question is
whether a defender can decide, before deployment and using only data they
already own, whether a given detector on a given data source should use the
divergence features, and whether deciding that way beats both fixed policies.

## Method

AVDS (integration/avds_experiment.py) runs three steps per detector, data
source and seed:

1. Split the defender's own clean data. The same temporal 60/40
   train/test split as Experiment 5 is kept. The 60% training portion is split
   again, temporally, into an inner-train part (first 45% of the stream) and a
   validation part (next 15%). The test portion is never read during
   selection.
2. Red-team each candidate on validation. The detector is trained on
   inner-train twice, once with and once without the divergence features.
   Each candidate is then attacked on the validation part with the project's
   own bounded false-data-injection attacks, both static and adaptive (the
   gradient-guided adversary queries the candidate being evaluated).
3. Pick by worst case. Divergence is kept only if its worst-case
   validation F1 (the lower of static and adaptive), averaged over the
   rehearsed attacks, is strictly higher. Ties keep the smaller feature set.
   One decision is made per detector and applied to every test attack, since
   a deployer cannot know in advance which attack will arrive. Worst case rather than average is used
   because Experiment 5's clearest effect of divergence was on robustness to
   the adaptive attacker, not on static accuracy.

The chosen configuration is retrained on the full 60% training portion and
evaluated on the test portion exactly as in Experiment 5. Same detector,
calibration, attack strength, attack ratio, and seeds. So the "never" and
"always" policies here are Experiment 5's two arms, and
scripts/avds_summary.py --exp5 ... checks, seed by seed, that they
reproduce Experiment 5's F1 values exactly.

Known and novel attacks. avds rehearses every attack in the defender's
library, which is the known-threat case. avds_novel is a stress test for an
attack outside the library: against test attack A, it is chosen from
validation runs of the other attack only, so any gain cannot come from
having rehearsed A.

Policies compared (all evaluated on the identical test portion and seeds):

| Policy | Divergence used |
|---|---|
| never | never (Experiment 5, divergence off) |
| always | always (Experiment 5, divergence on) |
| avds | chosen by AVDS, one choice per detector from all rehearsed attacks. The method under test |
| avds_novel | chosen by AVDS without rehearsing the tested attack (unseen-attack stress test) |
| oracle | whichever of never/always had the higher worst-case test F1 for that seed. Unattainable in practice; an upper bound |

Primary metric. Worst-case test F1, min(static F1, adaptive F1), per
(dataset, detector, attack, seed). AVDS is compared to each fixed policy with
the same paired, seed-matched Wilcoxon signed-rank test and bootstrap 95% CI
used in Experiment 5. Also reported: the rate at which AVDS makes the oracle's
choice, and AVDS's regret (oracle minus AVDS worst-case F1).

What would count as success. AVDS's worst-case F1 is at least as high as
the better fixed policy in most conditions, and significantly higher than
the worse one, without ever being significantly worse than both. If AVDS only
matches whichever fixed policy happens to be better, it is still useful,
since the deployer does not know in advance which one that is. If it is often
significantly worse than a fixed policy, the validation signal does not
transfer to test, and that is reported as a negative result.

## Pilot, and what it changed

A pilot (seeds 1-3, all five detectors, SUMO/NGSIM/pNEUMA, 2026-09-30,
results/ml/avds-pilot-v0.json) was run before the full experiment. It
confirmed that "never" and "always" reproduce Experiment 5 exactly (360 of
360 per-seed F1 values, max difference 0). It also changed the method in two
ways, recorded here because they were decided after seeing pilot results:

1. The first design chose leave-one-attack-out as the primary rule. In the
   pilot it always landed between the two fixed policies. Its largest loss was
   Mahalanobis on SUMO against congestion_spoof (0.383 vs 0.874 worst-case
   F1): divergence rescues that detector against that one attack only, so a
   choice learned from the other attack does not transfer. It is kept as
   avds_novel, the unseen-attack stress test, and not dropped.
2. A same-attack variant, chosen separately for each test attack, was
   removed. A deployer cannot know which attack will arrive, so it is not a
   deployable policy. It was replaced by one choice per detector using all
   rehearsed attacks, which is now the primary avds. Recomputed from the
   pilot's stored validation scores (no re-run), its pooled worst-case F1 was
   0.302 / 0.085 / 0.327 on SUMO or NGSIM or pNEUMA, against 0.237 / 0.078 /
   0.335 (never), 0.259 / 0.085 / 0.298 (always) and 0.306 / 0.085 / 0.346
   (oracle).

Because the rule was settled using pilot seeds 1-3, the full run on those
three sources uses seeds 4-33, so no result below re-scores data the rule
was shaped on. The ten further pNEUMA sessions were not used in the pilot.

## Data

- SUMO, NGSIM, pNEUMA (session 20181101_d1_0830_0900): the same
  40,000-message streams as Experiment 5, 30 seeds each (4-33, see above).
- Ten further pNEUMA sessions, 10 seeds each, to address Experiment 5's
  single-session limitation (§8.1 of the manuscript). Sessions are chosen by a
  fixed rule, not by inspecting results: drone d*i* (i = 1..10) once each, the
  recording day cycling through the four days (24, 29, 30 Oct, 1 Nov 2018),
  and the half-hour window cycling through the five morning windows. 29 Oct
  has no 10:30-11:00 window, so d10 takes that day's last window. The list
  is in scripts/run_avds_full.sh.

## Reproducing

    bash scripts/run_avds_full.sh # JOBS=4 by default; ~a day on a 4-core laptop
    python scripts/avds_summary.py results/ml/avds-sumo-30seed.json \
        results/ml/avds-ngsim-30seed.json results/ml/avds-pneuma-30seed.json \
        --exp5 sumo=results/ml/real-data-sumo-30seed.json \
               ngsim=results/ml/real-data-ngsim-30seed.json \
               pneuma=results/ml/real-data-pneuma-30seed.json

## Results

Filled in per source as the confirmatory run completes. Seeds 4-33; worst-case
F1 = min(static F1, adaptive F1) on the held-out test portion.

### SUMO (completed 2026-09-30, 3 h 22 min on 4 workers)

Reproduction: the never/always policies matched Experiment 5's per-seed
F1 on all 1,080 overlapping values (seeds 4-30), max difference 0.

| Detector or attack | never | always | avds | avds_novel | oracle | avds − never (p) | avds − always (p) | agrees w/ oracle |
|---|---|---|---|---|---|---|---|---|
| Isolation Forest or congestion | 0.495 | 0.610 | 0.594 | 0.574 | 0.613 | +0.099 (6.1e-05) | −0.015 (0.050) | 0.73 |
| Isolation Forest or clear-road | 0.176 | 0.119 | 0.153 | 0.130 | 0.193 | −0.023 (0.88) | +0.034 (0.069) | 0.67 |
| Autoencoder or congestion | 0.250 | 0.250 | 0.280 | 0.268 | 0.281 | +0.029 (0.036) | +0.030 (4.6e-05) | 0.93 |
| Autoencoder or clear-road | 0.134 | 0.134 | 0.150 | 0.150 | 0.151 | +0.017 (0.017) | +0.016 (1.5e-03) | 0.83 |
| LOF or congestion | 0.415 | 0.163 | 0.415 | 0.415 | 0.415 | 0 | +0.252 (1.9e-09) | 1.00 |
| LOF or clear-road | 0.457 | 0.318 | 0.457 | 0.457 | 0.457 | 0 | +0.138 (1.9e-09) | 1.00 |
| Mahalanobis or congestion | 0.379 | 0.873 | 0.873 | 0.494 | 0.873 | +0.494 (1.9e-09) | 0 | 1.00 |
| Mahalanobis or clear-road | 0.109 | 0.071 | 0.071 | 0.071 | 0.109 | −0.039 (1.9e-09) | 0 | 0.00 |
| EWMA residual or either | 0.024 | 0.024 | 0.024 | 0.024 | 0.024 | 0 | 0 | 1.00 |
| Pooled (300 units) | 0.246 | 0.259 | 0.304 | 0.261 | 0.314 | +0.058 [+0.040, +0.076], p = 3.9e-08 | +0.045 [+0.036, +0.056], p = 3.9e-17 | |

(Pooled CIs are bootstrap 95%; pooled units are not independent, so the
per-condition tests are the primary evidence.)

- AVDS beats both fixed policies, and closes about 82% of the gap
  between the better fixed policy and the unattainable oracle
  ((0.304 − 0.259) / (0.314 − 0.259)).
- It is never significantly worse than both fixed policies in any
  condition. Its largest per-condition cost is the price of one decision per
  detector: for Mahalanobis, validation correctly favours divergence
  (+0.494 against congestion spoofing), and the same choice costs −0.039
  against clear-road spoofing.
- avds_novel does not transfer. It is not significantly better than
  "never" (+0.014, p = 0.23) and only level with "always" (+0.002).
  Rehearsing one of these two attacks tells the defender little about the
  other: the same detector's best configuration often differs between them.
  This is reported as a limit of AVDS. It works for attacks in the defender's
  rehearsal library, not for arbitrary unseen ones.

### NGSIM (completed 2026-10-01, 5 h 00 min on 4 workers)

Reproduction: 1,080 of 1,080 overlapping per-seed F1 values match
Experiment 5 exactly.

| Detector or attack | never | always | avds | avds_novel | oracle | avds − never (p) | avds − always (p) |
|---|---|---|---|---|---|---|---|
| Isolation Forest or congestion | 0.106 | 0.119 | 0.119 | 0.114 | 0.120 | +0.013 (2.0e-05) | −0.000 (0.50) |
| Isolation Forest or clear-road | 0.122 | 0.123 | 0.123 | 0.123 | 0.127 | +0.001 (0.68) | +0.000 (0.89) |
| Autoencoder or congestion | 0.053 | 0.058 | 0.058 | 0.058 | 0.059 | +0.005 (9.9e-05) | +0.000 (0.18) |
| Autoencoder or clear-road | 0.055 | 0.067 | 0.067 | 0.063 | 0.068 | +0.012 (2.5e-05) | +0.000 (0.65) |
| LOF or congestion | 0.185 | 0.201 | 0.201 | 0.201 | 0.201 | +0.016 (2.6e-06) | −0.000 (0.32) |
| LOF or clear-road | 0.007 | 0.016 | 0.015 | 0.015 | 0.016 | +0.008 (2.6e-06) | −0.000 (0.32) |
| Mahalanobis or either | 0.07 | 0.07 | 0.07 | 0.07 | 0.07 | ≈0 (n.s.) | ≈0 (n.s.) |
| EWMA residual or either | 0.05-0.07 | same | same | same | same | ≈0 | ≈0 |
| Pooled (300 units) | 0.079 | 0.084 | 0.084 | 0.083 | 0.085 | +0.0055 [+0.0045, +0.0065], p = 1.5e-23 | −0.0001 [−0.0003, +0.0002], p = 0.27 |

- On NGSIM the correct fixed answer happens to be "always", since divergence
  helps a little almost everywhere. AVDS finds that without being told: it
  keeps divergence 83-97% of the time for the detectors where it matters, is
  indistinguishable from "always", and significantly beats "never".
- Absolute gains are small because detection on real NGSIM trajectories is
  hard for every method (worst-case F1 ≈ 0.08, cf. Experiment 5). The value
  AVDS adds here is not a large gain. It is avoiding the wrong fixed policy,
  since "never", which is right for LOF on SUMO, is wrong on NGSIM.
- avds_novel transfers here (+0.0046 over "never", p = 2.4e-19; −0.0010
  vs "always"), unlike on SUMO. On this source both attacks favour the same
  configuration, so rehearsing one is informative about the other.

### pNEUMA, session 20181101_d1_0830_0900 (completed 2026-10-01, 2 h 34 min)

Reproduction: 1,080 of 1,080 overlapping per-seed F1 values match
Experiment 5 exactly.

| Detector or attack | never | always | avds | avds_novel | oracle | avds − never (p) | avds − always (p) |
|---|---|---|---|---|---|---|---|
| Isolation Forest or congestion | 0.468 | 0.385 | 0.467 | 0.451 | 0.468 | −0.001 (0.32) | +0.081 (2.6e-06) |
| Isolation Forest or clear-road | 0.435 | 0.423 | 0.435 | 0.435 | 0.453 | +0.001 (0.32) | +0.013 (0.55) |
| Autoencoder or congestion | 0.305 | 0.293 | 0.317 | 0.299 | 0.321 | +0.012 (0.078) | +0.024 (2.2e-03) |
| Autoencoder or clear-road | 0.057 | 0.088 | 0.083 | 0.077 | 0.099 | +0.026 (6.5e-04) | −0.004 (0.011) |
| LOF or congestion | 0.207 | 0.144 | 0.207 | 0.207 | 0.207 | 0 | +0.063 (1.9e-09) |
| LOF or clear-road | 0.116 | 0.077 | 0.116 | 0.116 | 0.116 | 0 | +0.039 (1.9e-09) |
| Mahalanobis or congestion | 0.504 | 0.464 | 0.474 | 0.474 | 0.531 | −0.030 (0.078) | +0.010 (0.78) |
| Mahalanobis or clear-road | 0.721 | 0.634 | 0.667 | 0.667 | 0.737 | −0.053 (1.2e-03) | +0.034 (0.011) |
| EWMA residual or congestion | 0.194 | 0.182 | 0.194 | 0.191 | 0.194 | 0 | +0.012 (1.9e-09) |
| EWMA residual or clear-road | 0.251 | 0.248 | 0.251 | 0.251 | 0.251 | 0 | +0.003 (1.9e-09) |
| Pooled (300 units) | 0.326 | 0.294 | 0.321 | 0.317 | 0.338 | −0.0046 [−0.0096, +0.0002], p = 0.032 | +0.0275 [+0.0215, +0.0336], p = 9.4e-19 |

- Here the correct fixed answer is "never", the opposite of NGSIM. AVDS
  lands close to it and far above "always". It is slightly below "never":
  the Wilcoxon test gives p = 0.032 while the bootstrap CI of the mean just
  crosses zero, so the honest reading is "at most a small loss".
- That loss comes almost entirely from Mahalanobis. Validation keeps
  divergence for it in 50% of seeds against the oracle's 23%, with regret
  0.057-0.070. On this source the validation slice is a noisy guide for this
  detector. Every other detector is chosen at or near the oracle rate.

### Across the three sources

| Source | correct fixed policy | avds − better fixed | avds − worse fixed |
|---|---|---|---|
| SUMO | depends on detector | +0.045 | +0.058 |
| NGSIM | always | −0.0001 (n.s.) | +0.0055 |
| pNEUMA | never | −0.0046 (marginal) | +0.0275 |
| Mean worst-case F1 | never 0.217 · always 0.212 | avds 0.237 | oracle 0.246 (avds_novel 0.220) |

The best fixed policy differs between sources, so no fixed choice is safe.
AVDS never needs to know which one is right. It beats both fixed policies
where the right answer depends on the detector (SUMO). It matches or nearly
matches the right one where a single answer exists (NGSIM, pNEUMA). It always
clearly beats the wrong one. Averaged over sources it is above both fixed
policies and within 0.009 of the hindsight oracle. The unseen-attack variant
(avds_novel) keeps only part of this benefit, which bounds the claim: AVDS
needs the threat to be in the rehearsal library.

### Ten further pNEUMA sessions (completed 2026-10-01, 10 seeds each)

Sessions chosen by the fixed rule above, none used in the pilot. Pooled
worst-case F1 over five detectors × two attacks × ten seeds per session
(100 units each). Per-detector tables: results/ml/avds-pneuma-2018*.json,
or python scripts/avds_summary.py results/ml/avds-pneuma-2018*.json.

| Session (date, drone, window) | never | always | avds | oracle | avds − better fixed |
|---|---|---|---|---|---|
| 2018-10-24 d1 08:30 | 0.343 | 0.211 | 0.343 | 0.347 | −0.000 |
| 2018-10-29 d2 09:00 | 0.345 | 0.309 | 0.342 | 0.355 | −0.003 |
| 2018-10-30 d3 09:30 | 0.369 | 0.328 | 0.372 | 0.382 | +0.002 |
| 2018-11-01 d4 10:00 | 0.353 | 0.251 | 0.353 | 0.354 | 0.000 |
| 2018-10-24 d5 10:30 | 0.328 | 0.245 | 0.329 | 0.330 | +0.000 |
| 2018-10-29 d6 08:30 | 0.341 | 0.325 | 0.360 | 0.365 | +0.019 |
| 2018-10-30 d7 09:00 | 0.362 | 0.325 | 0.350 | 0.379 | −0.013 |
| 2018-11-01 d8 09:30 | 0.350 | 0.311 | 0.341 | 0.368 | −0.009 |
| 2018-10-24 d9 10:00 | 0.289 | 0.213 | 0.290 | 0.297 | +0.001 |
| 2018-10-29 d10 10:00 | 0.362 | 0.265 | 0.352 | 0.362 | −0.010 |
| Mean (10 sessions) | 0.344 | 0.278 | 0.343 | 0.354 | |

Treating each session as one independent unit (n = 10, paired Wilcoxon,
bootstrap 95% CI):

- avds − always: +0.065 [+0.045, +0.088], p = 0.002 (the smallest
  attainable at n = 10). AVDS beats "always" in all ten sessions.
- avds − never: −0.001 [−0.006, +0.005], p = 0.63, indistinguishable.
- AVDS is within 0.01 of the better fixed policy in 9 of 10 sessions and at
  or above it in 5. avds_novel: −0.005 vs never (p = 0.084), +0.061 vs
  always (p = 0.002).

"Never" is the better fixed policy in all ten sessions, consistent with the
main pNEUMA session. So these sessions do not show AVDS beating a fixed
policy. They show that across ten independent recordings (different drones,
days and times) it recovers the right one, and never falls far behind it. The
single-session limitation of Experiment 5 (§8.1) is addressed. The finding
that pNEUMA favours "never" holds across the city, not just in one recording.
As on the main session, the misses come mostly from Mahalanobis (sessions d2,
d7, d8) and, in d10, from EWMA-residual.

### Run notes

The laptop's battery reached its critical level at 17:45 on 2026-10-01, with
the last session (d10) about 70 minutes in. Windows put the machine to sleep
and the run resumed unchanged on wake at 22:33, finishing at 22:40. Sleep
suspends processes without altering their state, so results are unaffected.
Each unit is a deterministic function of (data, model, seed). The post-run
checks (scripts/post_avds_run.sh, report in
$SCS_DATA_DIR/logs/post-run-report.txt) passed: 176/176 tests, ruff and
mypy clean, Figure 4 written to docs/figures/fig4_avds.png.

## Why divergence helps some detectors and hurts others (mechanism)

scripts/mechanism_analysis.py rebuilds Experiment 5's exact pipeline for one
setting (SUMO, seed 4) and records, for Mahalanobis and LOF, with and without
divergence: the detector's score ROC AUC (threshold-free separability), its
F1 at the calibrated 5%-FPR threshold, the adaptive attacker's final
strengths, and each feature's attack-vs-benign AUC. Raw output:
results/ml/mechanism-sumo-{congestion_spoof,replay_stale}-seed4.json.

| Attack or detector or divergence | F1 static → adaptive | score AUC static → adaptive | attacker strength used (speed, occupancy) |
|---|---|---|---|
| congestion or Mahalanobis or off | 0.901 → 0.379 | 0.976 → 0.917 | (0.60, 0.29) |
| congestion or Mahalanobis or on | 0.875 → 0.874 | 0.973 → 0.974 | (0.60, 0.59) |
| congestion or LOF or off | 0.520 → 0.410 | 0.808 → 0.725 | (0.57, 0.40) |
| congestion or LOF or on | 0.169 → 0.199 | 0.546 → 0.570 | (0.58, 0.47) |
| replay or Mahalanobis or off | 0.421 → 0.415 | 0.712 → 0.711 | (0.60, 0.59) |
| replay or Mahalanobis or on | 0.097 → 0.092 | 0.715 → 0.716 | (0.60, 0.59) |
| replay or LOF or off | 0.442 → 0.390 | 0.742 → 0.709 | (0.56, 0.57) |
| replay or LOF or on | 0.313 → 0.257 | 0.651 → 0.616 | (0.55, 0.58) |

Three distinct mechanisms, measured rather than assumed:

1. Divergence closes the adaptive attacker's escape route (Mahalanobis,
   congestion). Without divergence, the 2D search keeps full speed bias and
   halves the occupancy bias (0.60 → 0.29). That slides the attack just under
   the threshold even though the detector still ranks attacks well (AUC
   0.917). With divergence, the same search finds no evading direction and
   ends at essentially full strength (0.60, 0.59). The occupancy change now
   also shows up as a twin residual that benign data rarely produces, so
   backing off one knob no longer hides the message.
2. Divergence moves the operating point, not the ranking (Mahalanobis,
   replay). Score AUC is unchanged (0.712 vs 0.715) while F1 at the
   calibrated threshold collapses (0.42 → 0.10). Benign divergence is
   heavy-tailed (SUMO training data: occupancy-divergence p99/p50 ≈ 51), so
   calibrating to a 5% benign false-positive rate pushes the threshold above
   where subtle, individually realistic replayed values score. Large or
   adaptive attacks still cross it. Subtle ones no longer do.
3. Divergence degrades separability itself (LOF). LOF's score AUC drops
   even against the static attacker (congestion 0.808 → 0.546, replay
   0.742 → 0.651). The failure is not adversarial. Our reading, a hypothesis
   not yet tested directly: LOF judges each point against its local
   neighbourhood, and the heavy benign tail gives attack points
   large-divergence benign neighbours to hide among. A global model such as
   Mahalanobis judges distance from the centre and is not fooled this way.
   Features are standardised (StandardScaler) for LOF, so this is not a
   feature-scaling artefact.

Implication for AVDS: no single rule ("divergence helps robust detectors",
"divergence hurts local detectors") holds across attacks. Mechanism 2 means
the same detector can gain against one attack family and lose against
another at a fixed false-positive budget. That is why the selection has to be
made empirically, per deployment, against the threat library. It also
suggests a cheap follow-up not tested here: calibrating the threshold on a
divergence-robust (e.g. clipped or rank-transformed) score could recover
mechanism-2 losses without giving up mechanism 1.

## Experiment 6b: four attacks (completed 2026-10-02, 6 h 25 min)

Experiment 6's avds_novel stress test was weak partly by construction: with
two attacks, "unseen" meant choosing from one other attack. Two further
bounded attacks were added to iot_sim/adversary.py:

- drift_congestion: the fake-congestion goal with the bias ramped from
  near zero over the attack window (speed −30 km/h, occupancy +0.6 at full
  strength and full ramp), so early messages sit inside normal variation.
- replay_stale: each attacked message moves toward a genuine reading
  recorded at least 5 minutes earlier, so every injected value is
  individually realistic and only its context is wrong.

Both use the same two strength knobs, so the adaptive adversary searches them
unchanged. The existing attacks are bit-identical: the RNG is drawn from
only for replay, and 1,200 of 1,200 overlapping per-seed values reproduce
Experiment 5 exactly. Run: bash scripts/run_avds4.sh, seeds 4-13 (the
4-attack pilot used seed 1), outputs results/ml/avds4-{sumo,ngsim,pneuma}.json.

| Source | never | always | avds | avds_novel | oracle | avds − never | avds − always |
|---|---|---|---|---|---|---|---|
| SUMO | 0.253 | 0.236 | 0.276 | 0.249 | 0.299 | +0.023 [+0.004, +0.043], p = 0.013 | +0.040 [+0.030, +0.051], p = 5.5e-12 |
| NGSIM | 0.078 | 0.083 | 0.084 | 0.083 | 0.085 | +0.005 [+0.004, +0.007], p = 2.2e-13 | +0.000 (p = 0.91) |
| pNEUMA | 0.292 | 0.233 | 0.293 | 0.278 | 0.297 | +0.001 [−0.000, +0.002], p = 0.079 | +0.060 [+0.049, +0.072], p = 1.0e-22 |
| Mean | 0.208 | 0.184 | 0.217 | 0.203 | 0.227 | | |

(Worst-case F1 pooled over 5 detectors × 4 attacks × 10 seeds = 200 units per
source.)

With a larger rehearsal library, AVDS improves. It is now at or above
both fixed policies on all three sources: significantly above both on SUMO,
above "never" and level with "always" on NGSIM, and on pNEUMA level with
"never" (+0.001) where it had been slightly below with two attacks
(−0.005). The pNEUMA gain comes from Mahalanobis. Replay and drift give
validation strong evidence against divergence for it (−0.29 and −0.19
worst-case F1 with divergence), so the choice that was a coin flip with two
attacks becomes consistent.

Unseen attacks remain the limit, and the mechanism explains why. Even
when chosen from three rehearsed attacks, avds_novel does not beat the
better fixed policy (mean 0.203 vs 0.208 for "never"). On SUMO the failure
is concentrated where mechanism (ii) predicts. For Mahalanobis, divergence is
worth +0.50 against congestion spoofing and +0.17 against drift, but −0.33
against replay and −0.04 against clear-road spoofing. Whether it helps
depends on the attack's magnitude regime, so the other attacks cannot vote
reliably on a held-out one. The claim therefore stays bounded: AVDS selects
well for threats represented in the rehearsal library, and adding attack
families to that library is what makes it robust.

## Post-hoc analyses of stored results (no new runs)

scripts/avds_analysis.py reuses the stored per-unit validation and test
scores (output: results/ml/avds-analysis.json).

Selection-rule ablation. Mean worst-case test F1 over sources when the
same validation scores are turned into a choice by different rules:

| Result family | worst-case (AVDS) | static-only | adaptive-only | mean(static, adaptive) | AVDS − static-only |
|---|---|---|---|---|---|
| 2 attacks, 30 seeds | 0.2365 | 0.2342 | 0.2365 | 0.2367 | +0.0023 [+0.0004, +0.0047], p = 0.0027 |
| 4 attacks, 10 seeds | 0.2174 | 0.2121 | 0.2174 | 0.2133 | +0.0053 [−0.0010, +0.0118], p = 0.20 |
| 10 pNEUMA sessions | 0.3430 | 0.3423 | 0.3430 | 0.3430 | +0.0007 [+0.0001, +0.0015], p = 0.031 |

- The worst-case rule makes exactly the same choices as adaptive-only.
  Adaptive validation F1 is never above static, so the minimum is always
  the adaptive score. In practice AVDS reduces to "rehearse against the
  adaptive attacker".
- Rehearsing only static attacks is consistently a little worse. The gap is
  significant with two attacks (n = 30) and across the pNEUMA sessions, and
  not significant with four attacks at n = 10. The adaptive part of the
  rehearsal therefore adds a small but consistent gain. How much any
  attack-based validation adds over validating with no attacks needs a new
  run (planned: E1 full).

Transfer of the decision. Applying the choice made on one source to
another loses on average 0.023 worst-case F1 relative to the target's own
choice (max 0.061, NGSIM-made choices applied to SUMO: 0.243 vs 0.304).
Across the ten pNEUMA sessions the average loss is 0.009 (max 0.099).
Decisions travel tolerably within one city and poorly between cities, so
AVDS should be run per deployment, not once per detector.

Multiple comparisons. Correcting the per-condition AVDS-vs-fixed tests
within each family:

| Family | tests | p < .05 raw | Holm | Benjamini-Hochberg |
|---|---|---|---|---|
| 2 attacks, n = 30 seeds | 46 | 26 | 19 | 24 |
| 4 attacks, n = 10 seeds | 80 | 37 | 0 | 30 |
| 10 pNEUMA sessions, n = 10 | 144 | 65 | 0 | 55 |

With n = 10 the exact Wilcoxon test cannot return p below 2/2^10 ≈ 0.002,
and Holm over 80 tests needs p < 0.0006. So "0 under Holm" is a resolution
floor of the test, not evidence of no effect. BH (false-discovery rate) is
used as the primary correction; Holm is reported for transparency. The
four-attack family would need ≥ 20 seeds for Holm to be informative.

## E1: baselines AVDS must beat (completed 2026-10-02)

integration/avds_baselines.py (run: bash scripts/run_avds_baselines.sh;
output results/ml/avds-baselines-{sumo,ngsim,pneuma}.json, merged by
scripts/avds_analysis.py) adds, on the same units as Experiment 6b (four
attacks, seeds 4-13):

- clean-validation selection: choose the configuration with the lower
  false-positive rate on the attack-free validation slice (no red team);
- fusion ensemble: run both configurations and alarm on the larger
  training-percentile of their scores, with the threshold set to the same 5%
  training false-positive budget; the adaptive adversary attacks the fused
  detector;
- AVDS-3: the same rehearsal, choosing among three candidates (without
  divergence, with divergence, ensemble) by worst-case validation F1, with
  ties going to the simplest.

| Source | never | always | clean-val | ensemble | AVDS | AVDS-3 | oracle (2) | oracle (3) |
|---|---|---|---|---|---|---|---|---|
| SUMO | 0.253 | 0.236 | 0.255 | 0.307 | 0.276 | 0.313 | 0.299 | 0.334 |
| NGSIM | 0.078 | 0.083 | 0.082 | 0.084 | 0.084 | 0.084 | 0.085 | 0.087 |
| pNEUMA | 0.292 | 0.233 | 0.237 | 0.258 | 0.293 | 0.293 | 0.297 | 0.298 |
| Mean | 0.208 | 0.184 | 0.191 | 0.216 | 0.217 | 0.230 | 0.227 | 0.240 |

Paired over all 600 (source, detector, attack, seed) units:

| Comparison | difference | 95% CI | p |
|---|---|---|---|
| AVDS − clean-validation | +0.026 | [+0.018, +0.034] | 5.6e-25 |
| AVDS − ensemble | +0.001 | [−0.006, +0.008] | 0.11 |
| AVDS-3 − AVDS | +0.013 | [+0.008, +0.017] | 9.7e-21 |
| AVDS-3 − ensemble | +0.014 | [+0.008, +0.019] | 2.4e-19 |
| AVDS-3 − never | +0.022 | [+0.016, +0.029] | 4.8e-30 |
| AVDS-3 − always | +0.046 | [+0.039, +0.052] | 2.1e-51 |

- Rehearsing attacks is essential. Choosing by attack-free false-positive
  rate (0.191) is worse than either fixed policy and far below AVDS. Clean
  data says nothing about which configuration survives an attacker.
- The ensemble is a strong single policy but not a safe one. It equals
  AVDS on average, being best on SUMO (0.307) and poor on pNEUMA (0.258),
  i.e. it has the same problem as any fixed choice.
- AVDS generalises to choosing among candidate configurations. Given the
  ensemble as a third option, the same rehearsal beats every alternative,
  exceeds the two-option oracle (0.227) and comes within 0.010 of the
  three-option oracle. The method is better described as adversarially
  validated configuration selection, with divergence as one dimension.
- Disclosure: adding the ensemble as an AVDS candidate was decided after
  the seed-1 pilot (results/ml/avds-baselines-pilot.json) showed the
  ensemble was competitive. The numbers above use seeds 4-13 only.

## E2: does a better twin remove the sign change? (completed 2026-10-02)

The window twin (TrafficDigitalTwin) predicts each message from the mean
of the last eight messages at the same intersection, from any vehicle. E2
repeats the four-attack run (seeds 4-13) with KalmanTrafficTwin
(digital_twin/kalman_twin.py). It tracks speed per vehicle and occupancy
per intersection with a local-level Kalman filter, reports divergence as
the normalised innovation (a z-score), and has noise parameters fixed a
priori. Output: results/ml/avds4-kalman-{sumo,ngsim,pneuma}.json.

| Twin | never | always | AVDS | avds_novel | oracle |
|---|---|---|---|---|---|
| window (original) | 0.208 | 0.184 | 0.217 | 0.203 | 0.227 |
| Kalman | 0.208 | 0.176 | 0.217 | 0.210 | 0.226 |

Mean divergence effect (always − never, worst-case F1) per detector:

| Detector | SUMO window → Kalman | NGSIM | pNEUMA |
|---|---|---|---|
| Isolation Forest | +0.008 → +0.051 | +0.007 → +0.007 | −0.051 → +0.032 |
| Autoencoder | +0.009 → −0.094 | +0.000 → −0.007 | −0.023 → −0.014 |
| LOF | −0.177 → −0.355 | +0.018 → +0.022 | −0.069 → −0.116 |
| Mahalanobis | +0.076 → +0.038 | 0 → 0 | −0.144 → −0.032 |
| EWMA residual | 0 → 0 | 0 → −0.002 | −0.010 → −0.005 |

A better twin does not make divergence a universal improvement. It
changes which detectors benefit. Isolation Forest gains on both SUMO and
pNEUMA, while the autoencoder flips from neutral to clearly harmful on SUMO
and LOF gets worse. "Always use divergence" is worse than with the crude
twin (0.176 vs 0.184). The sign change is therefore not an artefact of the
twin's quality. It is a property of how a residual feature interacts with
each detector's decision rule. AVDS is unaffected (0.217 with either twin),
and the unseen-attack variant improves slightly with the Kalman twin (0.210
vs 0.203). This strengthens the case for selecting per deployment rather than
fixing the feature set, even with a better twin.

## E3: attacking AVDS by poisoning its rehearsal data (completed 2026-10-02)

integration/avds_poisoning.py (run: bash scripts/run_avds_poisoning.sh;
output results/ml/avds-poisoning-{sumo,ngsim,pneuma}.json). An attacker
controlling devices during the defender's validation window adds poison
messages equal to 10% of that window. These are bounded attacks the defender
treats as normal traffic, so whichever configuration flags them is charged
false positives. The attacker knows the AVDS rule and, per unit, tries each
of the four attack types as poison. We report the attacker's best case: the
poison that most lowers the deployed detector's test worst-case F1.

Sanity check: the unpoisoned choice recomputed here equals the stored
four-attack AVDS choice in 150 of 150 units.

| Source | choices flipped | test cost of best poison, mean or max | never | always | AVDS | AVDS, poisoned |
|---|---|---|---|---|---|---|
| SUMO | 2/50 | 0.0002 / 0.011 | 0.253 | 0.236 | 0.276 | 0.275 |
| NGSIM | 16/50 | 0.0004 / 0.014 | 0.078 | 0.083 | 0.084 | 0.083 |
| pNEUMA | 12/50 | 0.023 / 0.180 | 0.292 | 0.233 | 0.293 | 0.270 |
| All | 30/150 (20%) | 0.008 / 0.180 | 0.208 | 0.184 | 0.217 | 0.209 |

Poisoned AVDS − never: +0.002 [−0.006, +0.010], p = 0.055; poisoned AVDS −
always: +0.025 [+0.021, +0.030], p = 1.3e-27.

- AVDS can be attacked. With 10% poison and full knowledge of the rule,
  an attacker flips one choice in five. Where the two options barely differ
  (NGSIM) flips are frequent but nearly free. Where they differ a lot
  (pNEUMA, chiefly Mahalanobis) a flip is expensive, up to 0.18 worst-case
  F1.
- On average, poisoning erases AVDS's advantage but does not push it below
  the best fixed policy. Poisoned AVDS falls from 0.217 to 0.209, level
  with "never" (0.208) and well above "always". On pNEUMA alone it falls
  below "never" (0.270 vs 0.292).
- Defence. The validation window is part of the attack surface and must
  be protected like training data. Rehearse on traffic from a trusted
  period, from authenticated devices only, or over several disjoint windows
  with a majority vote. These measures are recommended but not evaluated
  here.

## E4: sensitivity to the hand-set parameters (completed 2026-10-02)

bash scripts/run_avds_sensitivity.sh changes one setting at a time from the
four-attack configuration (seeds 4-8, all sources, 100 units per source).
Outputs: results/ml/avds4-sens-<variant>-<source>.json; summary
results/ml/avds-sensitivity-summary.json. The baseline row restricts the
Experiment 6b run to the same seeds.

| Setting | never | always | AVDS | oracle | AVDS − better fixed (95% CI), p |
|---|---|---|---|---|---|
| baseline (validation 15%, strength 0.6, FPR 5%, ratio 15%) | 0.209 | 0.181 | 0.218 | 0.227 | +0.009 [−0.000, +0.019], 1.5e-05 |
| validation 25% | 0.209 | 0.181 | 0.218 | 0.227 | +0.009 [−0.000, +0.019], 3.4e-05 |
| validation 10% | 0.209 | 0.181 | 0.217 | 0.227 | +0.008 [−0.001, +0.018], 9.4e-05 |
| attack strength 0.3 | 0.137 | 0.102 | 0.132 | 0.140 | −0.004 [−0.007, −0.001], 0.94 |
| attack strength 0.9 | 0.262 | 0.236 | 0.272 | 0.281 | +0.010 [+0.003, +0.017], 6.9e-06 |
| FPR budget 1% | 0.078 | 0.049 | 0.081 | 0.082 | +0.003 [+0.002, +0.005], 9.2e-07 |
| FPR budget 10% | 0.261 | 0.234 | 0.267 | 0.271 | +0.006 [+0.003, +0.010], 0.0068 |
| attack ratio 5% | 0.165 | 0.146 | 0.174 | 0.182 | +0.009 [+0.001, +0.017], 8.8e-05 |
| attack ratio 30% | 0.225 | 0.191 | 0.232 | 0.241 | +0.007 [−0.002, +0.016], 7.9e-05 |

(The better fixed policy is "never" in every setting. Several CIs touch
zero while the Wilcoxon p is small, because many paired differences are
exactly zero: AVDS often makes the same choice as "never".)

- The validation fraction does not matter (10%, 15% or 25% give the same
  result), so the 15% choice is not tuned.
- AVDS beats the better fixed policy in eight of nine settings, across
  attack strength, false-positive budget and attack prevalence, and it always
  beats the worse one by a wide margin.
- The exception is weak attacks (strength 0.3), where AVDS is slightly
  below "never" (−0.004). Weak attacks give the rehearsal a weak signal for
  telling configurations apart, so the choice is noisier than the gain it
  can deliver. AVDS's benefit grows with attack strength (+0.010 at 0.9).

## E5: a stronger adaptive adversary (completed 2026-10-03)

bash scripts/run_avds_strong_attacker.sh repeats the four-attack run
(seeds 4-8) with the adaptive adversary's gradient search tripled from 8 to
24 steps, in both rehearsal and test (--attacker-steps 24; output
results/ml/avds4-strong-<source>.json).

| Search budget | never | always | AVDS | avds_novel | oracle | AVDS − never |
|---|---|---|---|---|---|---|
| 8 steps (paper default) | 0.209 | 0.181 | 0.218 | 0.202 | 0.227 | +0.009, p = 1.5e-05 |
| 24 steps | 0.209 | 0.181 | 0.218 | 0.202 | 0.227 | +0.009, p = 1.3e-05 |

The setting took effect: the adaptive-attack F1 changed in 92 of 600
(unit, policy) cases. But the changes are negligible (mean −0.0005 on SUMO,
smaller elsewhere). A direct check (SUMO, Mahalanobis without divergence,
congestion spoofing) shows why. The search has converged by about step 8: the
attacker's final strengths are (0.600, 0.298) after 2 steps, and (0.600,
0.295) after both 8 and 24 steps, evading on 98.3% of attacked messages in
all three. The results are not limited by the adversary's search budget.
Not tested: a different family of adaptive attacker (other optimisers, more
than two manipulated fields, coordinated multi-device attacks).

## E6: compressing divergence's heavy tail (completed 2026-10-03)

Mechanism (ii) above says divergence hurts subtle attacks because its
heavy-tailed benign distribution raises the calibrated threshold. E6 tests
this directly. The four-attack run (seeds 4-13) is repeated with the
divergence features passed through log(1 + |x|), which is order-preserving
and compresses the tail (--divergence-transform log1p; output
results/ml/avds4-log1p-<source>.json).

| Divergence features | never | always | AVDS | avds_novel | oracle |
|---|---|---|---|---|---|
| raw | 0.208 | 0.184 | 0.217 | 0.203 | 0.227 |
| log1p | 0.208 | 0.190 | 0.218 | 0.208 | 0.227 |

log1p − raw: "always" +0.006 [+0.003, +0.010], p = 0.024; AVDS +0.000
[−0.001, +0.001], p = 0.91.

"Always divergence" worst-case F1 for the cases the mechanism analysis
singled out:

| Case | raw | log1p |
|---|---|---|
| pNEUMA, Mahalanobis, replay | 0.072 | 0.319 |
| SUMO, Mahalanobis, replay | 0.087 | 0.090 |
| SUMO, Mahalanobis, congestion (mechanism i) | 0.873 | 0.872 |
| SUMO, LOF, congestion | 0.164 | 0.185 |
| SUMO, autoencoder, congestion | 0.252 | 0.273 |

- Mechanism (ii) is partly confirmed. On pNEUMA, compressing the tail
  recovers most of Mahalanobis's loss against replay (0.07 → 0.32) and keeps
  the adaptive-attack rescue on SUMO intact (0.87). On SUMO the replay loss is
  not recovered (0.087 → 0.090), so the heavy tail is not the whole story
  there. A plausible additional cause, not tested: on SUMO the replayed
  values are close enough to the twin's prediction that divergence actively
  masks them.
- The fix helps the fixed policy, not AVDS. "Always" improves
  significantly but modestly. AVDS is unchanged, because it already avoids
  the configurations the transform repairs. A feature-level fix and AVDS
  address the same losses from two sides, and here they do not stack.

## E8: network loss, delay and duplication (completed 2026-10-03)

integration/network_impairment.py (run: bash scripts/run_network_impairment.sh;
output results/ml/network-<source>.json). Five link presets are applied
after attack injection (seeds 4-8, congestion and replay attacks, all
detectors, with and without divergence). Means over sources:

| Preset (loss, max delay, duplicates) | benign FPR, no div → div | worst-case F1, no div → div |
|---|---|---|
| ideal (0, 0, 0) | 0.049 → 0.049 | 0.230 → 0.200 |
| hrllc (1e-5, 10 ms, 0) | 0.049 → 0.050 | 0.426 → 0.423 |
| lossy (1%, 0.5 s, 0.5%) | 0.056 → 0.056 | 0.418 → 0.416 |
| degraded (5%, 2 s, 1%) | 0.213 → 0.214 | 0.311 → 0.312 |
| severe (10%, 5 s, 2%) | 0.430 → 0.429 | 0.253 → 0.259 |

Important methodological finding: message order within a second. The
attack design adds a malicious copy next to each targeted genuine message,
with the same sensor timestamp. SUMO has about 17 messages per timestamp. In
the "ideal" preset, as in all earlier experiments, same-timestamp messages are
processed in a fixed order (by message id), which puts every attack copy before
its genuine original (2,378 of 2,378 in a SUMO check). The "hrllc" preset adds
at most 10 ms of jitter and so effectively randomises that order. That alone
moves mean worst-case F1 from 0.230 to 0.426 (NGSIM 0.08 → 0.33). A direct
check on one SUMO configuration gives F1 0.533 under the fixed order, 0.322
under a random order, and 0.104 with copies always after originals. The
per-device change features (speed delta, inter-arrival) are computed against
whichever message of that device was processed last, so the convention
dominates absolute F1.

Consequences:
- All earlier comparisons between policies used the same convention, so
  they are internally fair. But absolute F1 values, and possibly which
  configuration wins, depend on it. NGSIM's low absolute F1 is largely
  this artefact.
- E13 below re-runs the main AVDS evaluation under a replacement attack
  model (the compromised device sends the false reading instead of the true
  one), which removes same-timestamp duplicates altogether.

Network finding, read against hrllc, the like-for-like baseline: 1%
loss with sub-second delay costs little (FPR 0.050 → 0.056). A degraded link
quadruples benign false alarms (→ 0.21) and a severe one multiplies them by
nine (→ 0.43). Late or out-of-order messages produce change and
inter-arrival features that look like attacks. Divergence neither causes nor
cures this: the FPR is the same with and without it at every preset. A
deployment on a poor link needs a reordering buffer or sequence-number
gating in front of the detector, whichever feature set it uses.

## E9: sequence-aware detectors (completed 2026-10-03; inject model)

--feature-history 5 feeds each detector the speed and occupancy of the
device's previous four messages alongside the current one: a windowed,
sequence-aware detector without a deep-learning dependency. It is not an
LSTM. Autoencoder and Isolation Forest, four attacks, seeds 4-13
(results/ml/avds4-temporal-<source>.json).

| Detector | input | never | always | AVDS | oracle |
|---|---|---|---|---|---|
| autoencoder | single message | 0.155 | 0.150 | 0.164 | 0.168 |
| autoencoder | window of 5 | 0.127 | 0.125 | 0.135 | 0.137 |
| isolation forest | single message | 0.276 | 0.264 | 0.283 | 0.294 |
| isolation forest | window of 5 | 0.175 | 0.179 | 0.192 | 0.196 |

The window lowers detection overall, sharply on SUMO (Isolation Forest
"never" 0.301 → 0.102, autoencoder 0.206 → 0.048), while it helps the
autoencoder on pNEUMA (0.195 → 0.261). AVDS still beats both fixed policies
for both windowed detectors. Caveat: this run uses the inject attack
model, whose same-timestamp duplicates (see E8) land inside the per-device
window, so windowed features are the most exposed to that artefact. A rerun
under the replacement model is queued (scripts/run_avds_temporal_replace.sh)
and supersedes these numbers for any claim about sequence-aware detection.

## E13: the main result under the replacement attack model (completed 2026-10-03)

E8 showed that the inject attack model, where a malicious copy sits next to
the genuine message at the same timestamp, makes absolute F1 depend on how
same-timestamp messages are ordered. E13 repeats the four-attack AVDS
evaluation (seeds 4-13, all sources) under a replacement model
(--attack-mode replace): the compromised device sends the false reading
instead of the true one, keeping its message id and stream position, so
there are no duplicates and no ordering convention to depend on. Output:
results/ml/avds4-replace-<source>.json.

| Attack model | never | always | AVDS | avds_novel | oracle |
|---|---|---|---|---|---|
| inject (Experiment 6b) | 0.208 | 0.184 | 0.217 | 0.203 | 0.227 |
| replace | 0.262 | 0.233 | 0.273 | 0.264 | 0.283 |

| Source (replace) | never | always | AVDS | avds_novel | oracle |
|---|---|---|---|---|---|
| SUMO | 0.294 | 0.267 | 0.320 | 0.292 | 0.343 |
| NGSIM | 0.108 | 0.114 | 0.115 | 0.114 | 0.117 |
| pNEUMA | 0.383 | 0.319 | 0.385 | 0.385 | 0.389 |

Replace model, paired over 600 units: AVDS − never +0.012 [+0.005, +0.019],
p = 2.6e-08; AVDS − always +0.040 [+0.033, +0.047], p = 4.3e-36.

- The main conclusion does not depend on the attack model. Under
  replacement, AVDS again beats both fixed policies, by slightly larger
  margins than under injection. The per-source pattern is unchanged: AVDS
  beats both on SUMO, matches "always" on NGSIM and matches "never" on
  pNEUMA.
- Absolute worst-case F1 is higher under replacement (mean "never" 0.262 vs
  0.208). The inject model's ordering convention made detection look harder
  than it is, as E8 indicated.
- The unseen-attack variant does better here (0.264, level with "never")
  than under injection (0.203).
- Recommendation for the manuscript: report the replacement model as the
  primary threat model, since it is how a compromised device behaves and has
  no ordering artefact. Keep the inject-model results as a robustness check.

## E13b: E1 baselines and AVDS-3 under the replacement model (completed 2026-10-03)

bash scripts/run_avds_baselines_replace.sh (output
results/ml/avds-baselines-replace-<source>.json) repeats E1 under the
replacement attack model, on the same units as E13.

| Source | never | always | clean-val | ensemble | AVDS | AVDS-3 | oracle (2) | oracle (3) |
|---|---|---|---|---|---|---|---|---|
| SUMO | 0.294 | 0.267 | 0.298 | 0.347 | 0.320 | 0.358 | 0.343 | 0.378 |
| NGSIM | 0.108 | 0.114 | 0.115 | 0.114 | 0.115 | 0.115 | 0.117 | 0.120 |
| pNEUMA | 0.383 | 0.319 | 0.322 | 0.356 | 0.385 | 0.385 | 0.389 | 0.391 |
| Mean | 0.262 | 0.233 | 0.245 | 0.272 | 0.273 | 0.286 | 0.283 | 0.296 |

| Comparison (600 paired units) | difference | 95% CI | p |
|---|---|---|---|
| AVDS − clean-validation | +0.029 | [+0.021, +0.037] | 1.7e-21 |
| AVDS − ensemble | +0.001 | [−0.006, +0.008] | 0.27 |
| AVDS-3 − AVDS | +0.012 | [+0.009, +0.016] | 4.5e-21 |
| AVDS-3 − ensemble | +0.014 | [+0.007, +0.020] | 1.5e-14 |
| AVDS-3 − never | +0.024 | [+0.016, +0.032] | 2.5e-23 |
| AVDS-3 − always | +0.052 | [+0.045, +0.059] | 3.7e-54 |

Every E1 conclusion replicates under the replacement model, with the same
ordering of methods. Clean-data selection is again below both fixed
policies. The ensemble again equals two-way AVDS. AVDS-3 again beats every
alternative, exceeds the two-option oracle, and comes within 0.010 of the
three-option oracle.

### E9b: sequence-aware detectors under the replacement model (completed 2026-10-03)

bash scripts/run_avds_temporal_replace.sh
(results/ml/avds4-temporal-replace-<source>.json) supersedes E9's
inject-model numbers.

| Detector | input (replace model) | never | always | AVDS | oracle |
|---|---|---|---|---|---|
| autoencoder | single message | 0.231 | 0.229 | 0.244 | 0.249 |
| autoencoder | window of 5 | 0.171 | 0.172 | 0.181 | 0.185 |
| isolation forest | single message | 0.284 | 0.267 | 0.290 | 0.299 |
| isolation forest | window of 5 | 0.183 | 0.182 | 0.199 | 0.202 |

The windowed input still lowers detection, sharply on SUMO (Isolation
Forest "never" 0.279 → 0.104, autoencoder 0.286 → 0.082), and slightly helps
the autoencoder on pNEUMA (0.302 → 0.319). So E9's finding is not an
ordering artefact. A plausible cause, not tested: once a vehicle's reading
is falsified, its next few genuine messages carry the false value in their
window and look anomalous too. That raises false positives and spreads the
alarm away from the attacked message itself. A naive sequence window is
therefore not a free improvement for message-level detection here. AVDS
still beats both fixed policies for both windowed detectors. Proper
sequence models (e.g. recurrent networks with message-level scoring) remain
untested.

## E12: which features each detector relies on (completed 2026-10-03)

scripts/feature_importance.py (output results/ml/feature-importance.json):
permutation importance, i.e. the drop in threshold-free score AUC when one
feature column is shuffled (5 repeats). Detectors with divergence, seed 4,
congestion and replay attacks, static and adaptive, all sources. Mean over
sources, attacks and modes:

| Feature | IF | autoencoder | LOF | Mahalanobis | EWMA |
|---|---|---|---|---|---|
| speed | 0.001 | 0.064 | 0.185 | 0.100 | −0.004 |
| occupancy | 0.036 | 0.048 | 0.184 | 0.080 | 0.010 |
| speed_delta | 0.088 | 0.089 | 0.077 | 0.065 | 0.088 |
| position_delta | 0.016 | 0.089 | 0.111 | 0.054 | −0.001 |
| interarrival | −0.002 | 0.014 | 0.057 | 0.000 | 0.039 |
| message_rate | −0.006 | −0.009 | 0.024 | −0.005 | 0.002 |
| profile_speed_violation | 0.009 | 0.037 | 0.053 | −0.002 | 0.021 |
| speed_divergence | 0.003 | 0.060 | 0.125 | 0.044 | −0.002 |
| occupancy_divergence | 0.019 | 0.038 | 0.121 | 0.067 | 0.005 |
| (base score AUC) | 0.728 | 0.608 | 0.608 | 0.727 | 0.573 |

- The per-device change feature (speed_delta) is the one every detector
  leans on most.
- LOF depends on almost every dimension at once, divergence included
  (0.12 each). This fits mechanism (iii): a local-density detector cannot
  ignore an uninformative or heavy-tailed feature, so extra dimensions blur
  its neighbourhoods. Isolation Forest, which splits on one feature at a
  time, barely uses divergence (0.003 / 0.019), consistent with divergence
  rarely hurting it.
- Divergence accounts for about 21-25% of total importance, similar for
  static and adaptive attacks.
- Caveat: E12 used the inject attack model. Change features such as
  speed_delta are exactly the ones exposed to E8's same-timestamp ordering
  artefact, so their importance here may be overstated. The ranking across
  detectors is the robust part of this result.

## To-do #1: supervised baseline, and a gradient-free attacker (completed 2026-10-03)

Question a reviewer will ask: if the defender can generate attacks for
rehearsal, why not train a supervised detector on them?
integration/supervised_baseline.py trains a random forest on benign
inner-train messages plus the four bounded attacks (static, replacement
model) applied to the validation slice, with divergence features. The
threshold is set at the 95th percentile of out-of-bag benign attack
probability, a 5% benign budget. It is scored on the same test portion and
seeds as E13, either with all four families seen in training ("known") or
with the tested family held out ("unseen").

Gradient masking check. Random forests and isolation forests have
step-shaped scores, which can starve a finite-difference attacker of
gradient. A gradient-free grid attacker was added
(AdversarialCampaign(search="grid"), --attacker-search grid). It tries
all 7×7 (speed, occupancy) strength pairs and keeps the strongest that
evades. Against the random forest it is clearly stronger: adaptive F1 for
known families falls from 0.557 (gradient) to 0.459 (grid). Against
unsupervised detectors it is sometimes stronger (LOF) and sometimes weaker
(Mahalanobis), so the fair score for every configuration is the minimum
over static, gradient-adaptive and grid-adaptive attack. The runs are
results/ml/supervised-grid-*.json and
results/ml/avds4-replace-grid-*.json (seeds 4-8).

Fair worst-case F1 (minimum over the three attack modes, replacement model,
seeds 4-8):

| Source | never | always | AVDS (robust) | oracle (2) | supervised, known | supervised, unseen | best unsupervised detector in hindsight |
|---|---|---|---|---|---|---|---|
| SUMO | 0.275 | 0.261 | 0.299 | 0.323 | 0.486 | 0.478 | 0.599 |
| NGSIM | 0.090 | 0.104 | 0.105 | 0.106 | 0.373 | 0.306 | 0.178 |
| pNEUMA | 0.317 | 0.231 | 0.318 | 0.319 | 0.486 | 0.435 | 0.452 |
| Mean | 0.227 | 0.198 | 0.240 | 0.250 | 0.448 | 0.406 | 0.410 |

AVDS (robust) − never +0.013 [+0.003, +0.023], p = 1.4e-04; − always +0.042
[+0.034, +0.051], p = 8.4e-22. Supervised (known) − best unsupervised in
hindsight +0.039 [−0.009, +0.083], p = 0.0036. Supervised (unseen) − best
unsupervised in hindsight −0.003 [−0.045, +0.036], p = 0.24. Supervised
(unseen) − AVDS averaged over detectors +0.166 [+0.141, +0.191], p = 3.1e-11.

What this means:
- AVDS's own conclusion survives the stronger attacker. Choosing
  divergence by rehearsal still beats both fixed policies when every
  configuration faces the worse of two adaptive attackers.
- A supervised detector trained on the rehearsal attacks is far stronger
  than a typical unsupervised detector, by about +0.17 to +0.21 worst-case
  F1. It is stronger still on known families (0.448), and about as good as
  the best unsupervised detector chosen in hindsight even on a held-out
  family (0.406 vs 0.410). The hindsight choice is unattainable in practice;
  the supervised result is not.
- The gradient attacker had overstated the supervised detector by about 0.1.
  Any claim about tree-based detectors needs the gradient-free attacker.
- Implication for the paper: "choose the divergence setting of an
  unsupervised detector" is a real but small effect next to "use the
  rehearsal attacks as training data". The paper must report this, and
  should either position AVDS as a selection layer over all candidate
  detectors, supervised ones included, or narrow its claim to settings where
  rehearsal attacks cannot be used for training.

## Path A: AVDS over all candidates, supervised included (completed 2026-10-03)

integration/avds_full.py scores a supervised random forest on the same
rehearsal slice as the unsupervised candidates. The forest is trained on
benign plus attacked inner-train messages, so it never sees the rehearsal
slice. scripts/avds_full_analysis.py then lets AVDS choose among 11
candidates: 5 unsupervised detectors × divergence on/off, plus the forest.
Every score is the worst case over static, gradient-adaptive and
grid-adaptive attack (replacement model, seeds 4-8, 60 units per setting).
Output: results/ml/avds-full-analysis.json.

| Setting | AVDS-full | forest alone | AVDS, unsupervised only | best fixed unsupervised (hindsight) | oracle |
|---|---|---|---|---|---|
| known families | 0.494 | 0.494 | 0.355 | 0.288 | 0.538 |
| held-out family | 0.371 | 0.437 | 0.282 | 0.288 | 0.490 |

- Known families: AVDS picks the forest in 60 of 60 units, so it adds
  nothing over using the forest directly.
- Held-out family: AVDS picks the forest in 48 of 60 units. In the other
  12 (mostly Mahalanobis with divergence, on SUMO) the rehearsal on the
  other three families favours an unsupervised candidate that then fails on
  the held-out family. AVDS-full is significantly worse than the forest
  alone: −0.066 [−0.105, −0.031], p = 0.0022.
- Conclusion: in this setting, training a supervised detector on the
  rehearsal attacks dominates selecting among unsupervised configurations.
  Selection by rehearsal adds no value once that detector is a candidate,
  and on held-out families it can be misled. This supersedes the
  framing of AVDS as the paper's main contribution.
- Open question that decides the paper's framing: all four attack
  families are bounded perturbations of speed and occupancy, so the
  held-out family is still close to the training families. Whether the
  forest's advantage survives a qualitatively different attack (e.g.
  stuck-at/frozen sensor values, timing manipulation, position spoofing),
  where unsupervised detection is designed to help, has not been tested.

## Qualitatively novel attacks (completed 2026-10-03)

Three attack families that change different fields from the four rehearsal
families, and that are never used in rehearsal or supervised training:
stuck_at (the device keeps reporting its own earliest reading),
time_shift (genuine values, timestamp moved forward by up to 10 s) and
position_spoof (genuine values, position displaced by up to 150 m).
Replacement model, seeds 4-8. Each configuration's score is its worst case
over static, gradient-adaptive and grid-adaptive attack (bash
scripts/run_novel_attacks.sh; outputs results/ml/novel-unsup-* and
results/ml/novel-rf-*). The forest is the one trained on the four
rehearsal families (inner-train attacks, as in path A).

| | sumo | ngsim | pneuma | mean |
|---|---|---|---|---|
| supervised forest | 0.359 | 0.248 | 0.439 | 0.349 |
| best fixed unsupervised in hindsight (LOF, no divergence) | 0.439 | 0.244 | 0.424 | 0.369 |
| unsupervised configurations, average | 0.291 | 0.115 | 0.301 | 0.236 |
| best unsupervised per unit (oracle) | 0.462 | 0.275 | 0.438 | 0.392 |

| Novel family | forest | LOF, no divergence | unsupervised average |
|---|---|---|---|
| stuck_at | 0.379 | 0.247 | 0.151 |
| time_shift | 0.306 | 0.333 | 0.224 |
| position_spoof | 0.362 | 0.528 | 0.331 |

Forest − LOF (no divergence): −0.020 [−0.070, +0.030], p = 0.088. Forest −
unsupervised average: +0.113 [+0.084, +0.144], p = 3.3e-09.

- The supervised forest loses about 30% on structurally novel attacks
  (0.494 on its training families → 0.349).
- On novel families a plain LOF matches it on average and wins clearly on
  position spoofing (0.528 vs 0.362). The forest wins on stuck-at sensors.
  No single detector dominates.
- AVDS cannot anticipate novel families (it picks the forest in 45 of 45
  units). Rehearsal can only reflect attacks one thought to rehearse.
- Divergence does not help here. The best unsupervised configuration on
  novel attacks is LOF without divergence.
- Synthesis: supervised training on rehearsed attacks is best against the
  families it was trained on. An unsupervised detector is a necessary
  complement for families nobody anticipated. The natural next test is a
  hybrid (supervised forest fused with LOF), evaluated on both known and
  novel families.

## Hybrid: supervised forest + LOF (completed 2026-10-04, seeds 4-8)

integration/hybrid_detector.py trains a supervised forest (on the four
rehearsal families) and a LOF without divergence on the same inner-train
data. The hybrid fuses them by max benign-reference percentile: the forest's
reference uses out-of-bag probabilities, and the threshold sits at the same
5% benign budget. All three detectors are scored in the same run on the four
rehearsal families and the three novel ones. Each score is the worst case
over static, gradient-adaptive and grid-adaptive attack (replacement
model). Output: results/ml/hybrid-<source>.json.

| Detector | rehearsal families (known) | novel families | all seven |
|---|---|---|---|
| supervised forest | 0.494 | 0.349 | 0.432 |
| LOF (no divergence) | 0.272 | 0.369 | 0.314 |
| hybrid | 0.505 | 0.370 | 0.447 |

Hybrid − forest: known +0.011 [+0.006, +0.017], p = 2.8e-04; novel +0.021
[+0.011, +0.031], p = 8.1e-05; all +0.015 [+0.010, +0.021], p = 8.1e-08.
Hybrid − LOF: known +0.234, p = 9.3e-11; novel +0.000 [−0.046, +0.048],
p = 0.35.

Per novel family: stuck_at forest 0.379 / LOF 0.241 / hybrid 0.390;
time_shift 0.306 / 0.335 / 0.308; position_spoof 0.362 / 0.532 / 0.411.

The hybrid keeps the forest's strength on known families, slightly above
it, and matches LOF on novel ones. It is never worse than either part on
average. It does not reach LOF on position spoofing (0.411 vs 0.532): the
max-percentile fusion spends part of the false-positive budget on the
forest. Disclosure: the hybrid was designed after seeing the
novel-attack results on these seeds. A confirmation run on fresh seeds 9-13
(results/ml/hybrid-confirm-*.json) is the evidence to cite.

### Hybrid confirmation on fresh seeds 9-13 (completed 2026-10-04)

Same procedure, seeds never used to design the hybrid
(results/ml/hybrid-confirm-<source>.json):

| Detector | known | novel | all seven |
|---|---|---|---|
| supervised forest | 0.491 | 0.345 | 0.428 |
| LOF (no divergence) | 0.274 | 0.371 | 0.315 |
| hybrid | 0.507 | 0.370 | 0.448 |

Hybrid − forest: known +0.016 [+0.011, +0.021], p = 2.1e-06; novel +0.025
[+0.015, +0.036], p = 1.6e-05; all +0.020 [+0.014, +0.026], p = 2.1e-10.
Hybrid − LOF: novel −0.001 [−0.047, +0.046], p = 0.42.

The hybrid result replicates on fresh seeds, within 0.005 of the design
seeds on every summary number. It is the confirmed headline: a supervised
detector trained on rehearsed attacks, fused with an unsupervised detector,
is best overall and never worse than either part on average.

### Hybrid on a second set of novel attacks (completed 2026-10-04, seeds 4-13)

Three more structurally different families, never used in training or
rehearsal: identity_spoof (genuine values sent under another vehicle's
identity), noise_injection (zero-mean random noise, no consistent
direction) and backdate (timestamp moved backward by up to 10 s). Output:
results/ml/hybrid-novel2-<source>.json.

| Detector | known (4 rehearsal families) | novel set 2 |
|---|---|---|
| supervised forest | 0.493 | 0.397 |
| LOF (no divergence) | 0.273 | 0.397 |
| hybrid | 0.506 | 0.461 |

Per family (forest or LOF or hybrid): identity_spoof 0.435 / 0.447 / 0.414;
noise_injection 0.467 / 0.231 / 0.448; backdate 0.289 / 0.513 / 0.521.

Hybrid − forest on novel set 2: +0.064, bootstrap 95% CI [+0.034, +0.098],
but Wilcoxon p = 0.23. Over pooled units the two tests disagree, so this
difference is reported as suggestive, not established. Hybrid − LOF: +0.064
[+0.040, +0.091], p = 0.0019.

Across both novel sets (six families) the hybrid has the best mean, and it
is never far behind the better part. Its one weak family is
identity_spoof, where it trails both parts slightly (−0.02 to −0.03). The
fusion's shared false-positive budget makes it a little less sensitive than
the better single detector on families where only one part reacts.

## Hybrid robustness and operator-level detection (completed 2026-10-04, seeds 4-8)

### Network impairment (results/ml/hybrid-network-<source>.json)

Mean over sources; worst-case F1 averaged over congestion, replay and
position-spoof attacks.

| Link | forest: FPR or F1 | LOF: FPR or F1 | hybrid: FPR or F1 |
|---|---|---|---|
| hrllc | 0.056 / 0.451 | 0.069 / 0.373 | 0.061 / 0.479 |
| lossy (1%, 0.5 s) | 0.059 / 0.449 | 0.084 / 0.370 | 0.074 / 0.471 |
| degraded (5%, 2 s) | 0.131 / 0.401 | 0.410 / 0.299 | 0.367 / 0.342 |
| severe (10%, 5 s) | 0.251 / 0.346 | 0.763 / 0.269 | 0.687 / 0.286 |

On good links the hybrid is best. On degraded links it inherits LOF's
fragility: late and out-of-order messages look anomalous to LOF, so
benign false positives explode, while the forest degrades far more
gracefully. Deployment implication: a reordering/de-duplication buffer is
needed in front of the hybrid, or the system should fall back to the forest
alone when link quality degrades.

### Training-data poisoning (results/ml/hybrid-poisoning-<source>.json)

The attacker slips attack messages labelled as normal into the defender's
training stream.

| Poison rate | forest | LOF | hybrid |
|---|---|---|---|
| 0% | 0.452 | 0.373 | 0.479 |
| 5% | 0.491 | 0.340 | 0.469 |
| 10% | 0.399 | 0.326 | 0.412 |

At 10% poison every detector loses 0.05-0.07. The hybrid stays best but its
lead shrinks. The forest's rise at 5% is not monotone and probably reflects
the poisoned benign set moving its out-of-bag threshold; it should not be
read as poisoning helping. The training window, like the rehearsal window,
is an attack surface.

### Episode-level detection (results/ml/episodes-<source>.json)

20 vehicles per test stream compromised for 30 s each (every message
replaced). Mean over sources and attacks; static or grid-adaptive attacker.

| Detector | alarm rule | episodes detected | median delay | device-window F1 | false alarms per vehicle-hour |
|---|---|---|---|---|---|
| forest | raw | 0.95 / 0.94 | 1.2 / 1.8 s | 0.19 / 0.19 | ~85 |
| LOF | raw | 0.94 / 0.88 | 2.0 / 2.6 s | 0.20 / 0.19 | ~74 |
| hybrid | raw | 0.97 / 0.96 | 1.2 / 1.3 s | 0.20 / 0.20 | ~87 |
| forest | 2-of-3 | 0.76 / 0.87 | 4.9 / 5.4 s | 0.30 / 0.32 | ~32 |
| LOF | 2-of-3 | 0.69 / 0.73 | 4.7 / 6.0 s | 0.25 / 0.25 | ~31 |
| hybrid | 2-of-3 | 0.78 / 0.85 | 4.2 / 4.3 s | 0.31 / 0.32 | ~31 |

(False alarms per vehicle-hour = alarm events per hour on the attack-free
stream divided by observed vehicle-hours: about 300 vehicles and 4.2-4.4
vehicle-hours per test stream.)

- Compromised vehicles are found, and found fast. The hybrid flags
  96-97% of 30-second compromises, with a median first alarm about 1.3 s
  into the episode, including against the adaptive attacker.
- But the false-alarm burden is not operational. A 5% per-message
  false-positive budget becomes about 80-90 alarm events per vehicle-hour,
  and still about 30 with a 2-of-3 persistence rule. This is the honest
  answer to "is low message-level F1 practically meaningful?": detection
  power is good, alarm precision is the bottleneck. A deployable system
  needs a much lower per-message budget or stronger temporal aggregation.
  The trade-off curve (budget × persistence rule) is the next measurement.

## Alarm trade-off: false-positive budget × persistence rule (completed 2026-10-04)

integration/alarm_tradeoff.py (output results/ml/alarm-tradeoff-<source>.json)
repeats the episode evaluation at per-message budgets of 5%, 2%, 1% and 0.5%.
Thresholds are set directly at benign-score quantiles, so every budget is met.
At each budget it applies k-of-n persistence rules (an alarm when k of a
vehicle's last n messages are flagged). The grid-adaptive attacker is re-run
against the detector at each budget. Mean over sources, seeds 4-8, three
attacks, static and adaptive. Cells: episode detection rate or mean of
per-run median delay (s) / false-alarm events per vehicle-hour.

| Detector, budget | 1 of 1 | 2 of 3 | 3 of 5 | 4 of 5 |
|---|---|---|---|---|
| forest 5% | 0.94 / 1.5 / 85.3 | 0.81 / 5.2 / 32.0 | 0.75 / 7.0 / 14.2 | 0.67 / 7.2 / 3.8 |
| forest 2% | 0.88 / 2.6 / 50.3 | 0.74 / 6.0 / 11.6 | 0.67 / 6.2 / 4.0 | 0.62 / 6.6 / 0.8 |
| forest 1% | 0.83 / 3.2 / 29.7 | 0.69 / 4.9 / 4.9 | 0.64 / 5.3 / 1.4 | 0.56 / 7.5 / 0.2 |
| forest 0.5% | 0.77 / 3.5 / 16.9 | 0.65 / 5.2 / 2.0 | 0.59 / 6.1 / 0.5 | 0.48 / 8.5 / 0.0 |
| LOF 5% | 0.93 / 2.3 / 78.1 | 0.74 / 5.2 / 35.4 | 0.63 / 6.6 / 20.4 | 0.52 / 8.1 / 13.0 |
| LOF 2% | 0.69 / 5.3 / 39.7 | 0.50 / 7.5 / 14.1 | 0.39 / 7.5 / 8.2 | 0.31 / 9.9 / 5.3 |
| LOF 1% | 0.60 / 6.5 / 22.6 | 0.37 / 9.6 / 7.4 | 0.31 / 8.6 / 3.9 | 0.21 / 12.7 / 3.0 |
| LOF 0.5% | 0.36 / 9.9 / 14.1 | 0.23 / 10.3 / 4.2 | 0.17 / 8.0 / 2.2 | 0.12 / 11.1 / 1.4 |
| hybrid 5% | 0.96 / 1.3 / 86.6 | 0.82 / 4.3 / 31.5 | 0.75 / 5.2 / 16.5 | 0.68 / 6.3 / 8.7 |
| hybrid 2% | 0.92 / 1.8 / 47.4 | 0.76 / 4.7 / 12.7 | 0.69 / 5.9 / 5.5 | 0.60 / 8.0 / 3.4 |
| hybrid 1% | 0.85 / 3.4 / 28.8 | 0.70 / 6.0 / 6.5 | 0.64 / 5.4 / 3.0 | 0.54 / 7.4 / 1.5 |
| hybrid 0.5% | 0.81 / 4.1 / 16.4 | 0.66 / 5.7 / 2.1 | 0.58 / 6.0 / 0.5 | 0.50 / 8.6 / 0.3 |

- False alarms can be cut by two orders of magnitude, from about 86 to
  under 1 per vehicle-hour, by combining a lower per-message budget with
  persistence.
- At about one false alarm per vehicle-hour, roughly 60% of 30-second
  compromises are caught, in about 5-7 s. For example: forest 1% + 3-of-5
  gives 0.64 / 5.3 s / 1.4; forest 2% + 4-of-5 gives 0.62 / 6.6 s / 0.8;
  hybrid 0.5% + 3-of-5 gives 0.58 / 6.0 s / 0.5.
- The hybrid's advantage is confined to permissive operating points. At
  strict budgets the forest alone matches or beats it. LOF degrades fastest
  as the budget tightens, so it contributes little once false alarms must be
  rare.
- Operational reading: even one false alarm per vehicle-hour means
  hundreds of alarms per hour for a few hundred vehicles. The detector
  output should feed a triage or corroboration stage (e.g. cross-checking
  neighbouring vehicles or roadside sensors), not raise operator alerts
  directly.

## Published-method baselines (completed 2026-10-06, seeds 4-13)

integration/sota_baselines.py (output results/ml/sota-<source>.json)
re-implements three established approaches on the same pipeline, budget
(5% benign FPR) and worst-case scoring (static, gradient-adaptive and
grid-adaptive; replacement model), on all ten attack families:

- plausibility checks + kNN, adapted from So, Sharma and Petit (ICMLA 2018;
  theirs classifies whole sender-receiver interactions from six features,
  ours classifies single messages with k = 15):
  movement consistency |Δposition − speed·Δt| and implied acceleration,
  added to the message features;
- Kalman filter + chi-squared residual test, the classical CPS false-data
  detector (normalised innovations from KalmanTrafficTwin);
- histogram gradient boosting, a strong supervised tabular baseline.

| Detector | known (4) | novel A (3) | novel B (3) | all ten | sumo | ngsim | pneuma |
|---|---|---|---|---|---|---|---|
| hybrid (forest + LOF) | 0.506 | 0.370 | 0.461 | 0.452 | 0.460 | 0.392 | 0.503 |
| gradient boosting | 0.506 | 0.359 | 0.391 | 0.427 | 0.457 | 0.326 | 0.499 |
| supervised forest | 0.493 | 0.347 | 0.397 | 0.420 | 0.430 | 0.345 | 0.485 |
| plausibility + kNN | 0.544 | 0.322 | 0.350 | 0.419 | 0.528 | 0.297 | 0.433 |
| LOF | 0.273 | 0.370 | 0.397 | 0.339 | 0.454 | 0.183 | 0.381 |
| Kalman + chi-squared | 0.185 | 0.117 | 0.177 | 0.162 | 0.338 | 0.073 | 0.075 |

Hybrid − gradient boosting +0.024 [+0.013, +0.036], p = 0.013; hybrid −
forest +0.032 [+0.022, +0.042], p = 2.1e-11; hybrid − plausibility+kNN
+0.033 [+0.014, +0.052], Wilcoxon p = 0.19 (suggestive only); hybrid −
Kalman chi-squared +0.290, p = 7.8e-47.

- The hybrid is best overall. Every supervised method, including the
  published plausibility approach, shows the same pattern: strong on
  rehearsed families and weaker on novel ones.
- Physical plausibility checks are the strongest single signal on
  rehearsed attacks (0.544 vs 0.506), which makes them a natural
  candidate to add to the hybrid's supervised part.
- The classical Kalman/chi-squared residual detector collapses under
  adaptive attack (0.162 overall; 0.07 on NGSIM and pNEUMA). Bounded
  attacks that stay within the innovation's expected range evade it, and
  real driving noise inflates its benign residuals. This matches §6.4: on
  real data, twin residuals are a weak detection signal on their own.

## Hybrid+: plausibility features in the hybrid's forest (completed 2026-10-06)

integration/hybrid_plus.py (outputs results/ml/hybrid-plus-<source>.json
and results/ml/hybrid-plus-confirm-<source>.json; driver
scripts/run_hybrid_plus.sh). Hybrid+ uses the same LOF part, max-percentile
fusion and 5% benign budget as the hybrid. Its forest is trained on the
message features plus the two plausibility checks from sota_baselines
(movement consistency and implied acceleration). forest_plus is that forest
alone. Scoring is the worst case over static, gradient-adaptive and
grid-adaptive attack (replacement model) on all ten families.

Selection caveat: Hybrid+ was designed after seeing the seed 4-13 SOTA
results, so seeds 4-13 are the design set. The claim rests on fresh seeds
14-23, run once, with hybrid, hybrid+, forest+ and plausibility+kNN all
re-scored on the same units (3 sources × 10 seeds = 30 paired units).

| Detector | seeds | known (4) | novel A (3) | novel B (3) | all ten | sumo | ngsim | pneuma |
|---|---|---|---|---|---|---|---|---|
| hybrid+ | 4-13 | 0.542 | 0.400 | 0.470 | 0.478 | 0.489 | 0.416 | 0.530 |
| forest+ | 4-13 | 0.532 | 0.402 | 0.426 | 0.461 | 0.501 | 0.372 | 0.511 |
| hybrid | 4-13 | 0.506 | 0.370 | 0.461 | 0.452 | 0.460 | 0.392 | 0.503 |
| plausibility + kNN | 4-13 | 0.544 | 0.322 | 0.350 | 0.419 | 0.528 | 0.297 | 0.433 |
| hybrid+ | 14-23 | 0.537 | 0.398 | 0.467 | 0.474 | 0.487 | 0.409 | 0.526 |
| forest+ | 14-23 | 0.527 | 0.400 | 0.428 | 0.459 | 0.497 | 0.368 | 0.513 |
| hybrid | 14-23 | 0.503 | 0.367 | 0.460 | 0.449 | 0.460 | 0.388 | 0.501 |
| plausibility + kNN | 14-23 | 0.544 | 0.300 | 0.354 | 0.414 | 0.528 | 0.296 | 0.417 |

Paired differences on the confirmation seeds 14-23 (mean, wins out of 30,
Wilcoxon p):

| Comparison | known | novel A | novel B | all ten |
|---|---|---|---|---|
| hybrid+ − hybrid | +0.033, 29/30, p < 1e-4 | +0.031, 30/30, p < 1e-4 | +0.007, 22/30, p = 1e-4 | +0.025, 30/30, p < 1e-4 |
| hybrid+ − plausibility+kNN | −0.007, 10/30, p = 0.09 | +0.098, 28/30, p < 1e-4 | +0.113, 20/30, p = 7e-4 | +0.061, 20/30, p = 1e-4 |
| hybrid+ − forest+ | +0.010, 20/30, p = 0.06 | −0.002, 17/30, p = 0.94 | +0.044, 20/30, p = 0.006 | +0.017, 20/30, p = 0.001 |

- Confirmed on fresh seeds. Hybrid+ beats the original hybrid on every
  one of the 30 confirmation units (+0.025 overall). The gain on fresh seeds
  matches the design seeds (+0.026), so this is not a selection artefact.
- It closes the gap on rehearsed attacks without giving up novel ones.
  Hybrid+ ties plausibility+kNN on known families (0.537 vs 0.544, n.s.) and
  is far ahead on both novel sets (+0.10 and +0.11). It is now the best
  detector overall: 0.474 vs 0.414.
- Plausibility also helps on unseen families. forest+ improves novel A
  over the plain forest (0.400 vs 0.347 on seeds 4-13). Physical-consistency
  checks generalise to stuck-at, time-shift and position spoofing, which
  break the same motion constraints.
- LOF still matters for novel B. Adding LOF to forest+ helps mainly on
  identity spoof, noise injection and backdating (+0.044, p = 0.006). The
  fusion argument from the hybrid section still holds.
- Limitation: on SUMO, plausibility+kNN remains best (0.528 vs 0.487).
  Simulated motion is noise-free, so a plausibility classifier alone already
  separates the classes, and LOF's extra alarms there cost precision. On
  the two real-data sources Hybrid+ leads clearly.

## VeReMi Extension benchmark (completed 2026-10-14)

integration/veremi_benchmark.py (output results/ml/veremi-benchmark.json;
loader evaluation/v2x_datasets.py). This is the standard simulated
misbehaviour benchmark (Kamel et al., F2MD, Luxembourg scenario; the eleven
14:00-16:00 files for position, speed, replay, delay and eventual-stop
attacks). The attacks are the dataset's own and are static: no attacker
adapts to the detector, so this complements the adaptive results above; it
does not replace them.

Protocol: each attack file is cut into four 1,500 s windows; in each window
the first 45% of messages train and the last 40% test (about 13,400 test
messages, 31% from attacker vehicles). Messages are labelled by sender.
Thresholds target a 5% benign false-positive rate on training data. For a
test window of attack type t, attack examples for training come from all
eleven types ("seen"), from the other ten ("unseen type"), or only from
types outside t's category ("unseen category"; the four position types
are siblings, as are the four speed types). 43 units (one file is one hour
long, so it has fewer windows).

| Detector | seen | unseen type | unseen category | benign FPR on test |
|---|---|---|---|---|
| hybrid+ | 0.796 | 0.767 | 0.756 | 0.090 |
| forest+ | 0.795 | 0.761 | 0.748 | 0.101 |
| hybrid | 0.786 | 0.749 | 0.733 | 0.100 |
| supervised forest | 0.779 | 0.735 | 0.615 | 0.118 |
| plausibility + kNN | 0.618 | 0.536 | 0.425 | 0.048 |
| LOF | 0.629 | 0.629 | 0.629 | 0.071 |

Mean F1 over 43 units. Paired, hybrid+ minus: hybrid +0.010 / +0.018 /
+0.023 (p ≤ 6e-05 in all three settings); forest +0.017 / +0.031 / +0.141
(p ≤ 1.3e-04); forest+ +0.001 (p = 0.12) / +0.005 (p = 0.016) / +0.008
(p = 0.0013); LOF +0.167 / +0.137 / +0.127 (p ≤ 6.5e-04).

Per attack type, F1 as seen or unseen type or unseen category:

| Attack type | category | hybrid+ | forest | plausibility+kNN (seen or category) | LOF |
|---|---|---|---|---|---|
| ConstPos | position | 0.91 / 0.89 / 0.90 | 0.88 / 0.86 / 0.88 | 0.58 / 0.45 | 0.72 |
| ConstPosOffset | position | 0.27 / 0.21 / 0.22 | 0.30 / 0.23 / 0.23 | 0.18 / 0.16 | 0.17 |
| RandomPos | position | 0.91 / 0.91 / 0.92 | 0.89 / 0.89 / 0.90 | 0.94 / 0.94 | 0.93 |
| RandomPosOffset | position | 0.90 / 0.90 / 0.90 | 0.87 / 0.82 / 0.86 | 0.30 / 0.32 | 0.90 |
| ConstSpeed | speed | 0.91 / 0.90 / 0.89 | 0.88 / 0.87 / 0.47 | 0.87 / 0.06 | 0.91 |
| ConstSpeedOffset | speed | 0.88 / 0.87 / 0.86 | 0.84 / 0.76 / 0.36 | 0.62 / 0.15 | 0.83 |
| RandomSpeed | speed | 0.91 / 0.91 / 0.90 | 0.88 / 0.88 / 0.56 | 0.93 / 0.46 | 0.92 |
| RandomSpeedOffset | speed | 0.85 / 0.81 / 0.64 | 0.82 / 0.77 / 0.45 | 0.43 / 0.41 | 0.65 |
| EventualStop | stop | 0.80 / 0.68 / 0.68 | 0.77 / 0.67 / 0.67 | 0.60 / 0.49 | 0.14 |
| DataReplay | replay | 0.76 / 0.69 / 0.69 | 0.78 / 0.68 / 0.68 | 0.62 / 0.55 | 0.68 |
| DelayedMessages | delay | 0.68 / 0.68 / 0.68 | 0.67 / 0.67 / 0.67 | 0.68 / 0.68 | 0.11 |

- Hybrid+ is best in all three settings on the standard benchmark, and
  loses little when a type or a whole category is withheld (0.796 → 0.756).
- The plain supervised forest loses a fifth when a category is withheld
  (0.779 → 0.615); on the speed category it halves (0.88 → 0.47 on
  ConstSpeed). Withholding a single type costs it little (0.735), because
  a sibling type is still in training. Plausibility features (forest+) and
  the LOF part each recover most of that loss.
- No single part wins every type. LOF matches the supervised detectors
  on the random and speed types but fails on EventualStop and
  DelayedMessages (0.14, 0.11), where supervision is needed.
- Constant position offset defeats every detector (0.17-0.30). A
  constant shift keeps all kinematics consistent for a single sender;
  PAMPOS reports the same weakness on this attack (F1 0.19).
- Caveats. The attacker is static. Labels are per sender, so an
  EventualStop attacker's early genuine messages count as attacks. The
  realised benign false-positive rate on test is 0.09-0.12 for the
  forest-based detectors, above the 5% target set on training data, and
  0.048 for plausibility+kNN, so the detectors are not compared at exactly
  equal alarm rates. Our plausibility+kNN is adapted from So et al., not
  their six-feature, per-interaction design.

## Leave-one-family-out (completed 2026-10-14, seeds 4-13)

integration/leave_one_out.py (output results/ml/leave-one-out-<source>.json,
driver scripts/run_leave_one_out.sh). Each of the ten families takes a
turn as the unseen one: the supervised parts are trained on the other nine
and scored on it ("unseen"). The same models trained on all ten give the
"seen" score. Worst case over static, gradient-adaptive and grid-adaptive
attack, replacement model, 5% benign budget; 30 units (3 sources × 10 seeds).

| Detector | seen (trained on all ten) | unseen (held out) | change |
|---|---|---|---|
| hybrid+ | 0.459 | 0.446 | −0.013 (−3%) |
| forest+ | 0.449 | 0.435 | −0.014 (−3%) |
| hybrid | 0.437 | 0.420 | −0.017 (−4%) |
| supervised forest | 0.426 | 0.406 | −0.020 (−5%) |
| LOF (no attack data) | 0.339 | 0.339 | 0 |

Unseen score by held-out family, and the forest's seen → unseen change:

| Family | forest | forest+ | hybrid | hybrid+ | LOF | forest seen → unseen |
|---|---|---|---|---|---|---|
| congestion_spoof | 0.504 | 0.545 | 0.497 | 0.536 | 0.302 | 0.505 → 0.504 |
| clear_road_spoof | 0.454 | 0.526 | 0.444 | 0.507 | 0.244 | 0.499 → 0.454 |
| drift_congestion | 0.453 | 0.499 | 0.423 | 0.464 | 0.258 | 0.458 → 0.453 |
| replay_stale | 0.433 | 0.478 | 0.431 | 0.473 | 0.287 | 0.442 → 0.433 |
| stuck_at | 0.335 | 0.434 | 0.336 | 0.431 | 0.241 | 0.345 → 0.335 |
| time_shift | 0.276 | 0.273 | 0.316 | 0.310 | 0.336 | 0.298 → 0.276 |
| position_spoof | 0.404 | 0.381 | 0.447 | 0.427 | 0.533 | 0.418 → 0.404 |
| identity_spoof | 0.429 | 0.395 | 0.429 | 0.399 | 0.447 | 0.412 → 0.429 |
| noise_injection | 0.416 | 0.474 | 0.405 | 0.459 | 0.231 | 0.464 → 0.416 |
| backdate | 0.356 | 0.349 | 0.469 | 0.451 | 0.513 | 0.416 → 0.356 |

Unseen, by source: SUMO forest 0.369 / forest+ 0.423 / hybrid 0.397 /
hybrid+ 0.431 / LOF 0.454; NGSIM 0.381 / 0.394 / 0.378 / 0.394 /
0.183; pNEUMA 0.468 / 0.489 / 0.485 / 0.512 / 0.381.

Paired on unseen (30 units): hybrid+ − hybrid +0.026 (30/30, p = 1.9e-09);
hybrid+ − forest +0.040 (29/30, p = 3.7e-09); hybrid+ − forest+ +0.010
(25/30, p = 6.3e-05); hybrid+ − LOF +0.107 (20/30, p = 9.9e-05).

This corrects an earlier reading. The novel-attack results above
compared four rehearsed families (forest 0.49) with three never-rehearsed
ones (0.35) and called the gap the cost of novelty. Leave-one-out shows
that most of that gap is not novelty:

- Withholding one family out of ten costs only 3-5%. The forest is
  nearly as good on a family it has never seen as on the same family when
  trained on it.
- The hard families are hard even when rehearsed. Trained on them, the
  forest still reaches only 0.298 on time shift, 0.345 on stuck-at and
  0.416-0.418 on backdate and position spoof, against about 0.50 on the
  spoofing families. The earlier "novel" sets happened to be the families
  whose manipulation the message features expose least.
- So the dividing line is the mechanism, not whether it was rehearsed.
  Families that change speed and occupancy values are caught by the
  supervised parts (plausibility features add 0.03-0.10). Families that
  change time, position or identity are caught better by LOF, with or
  without rehearsal. No part wins both groups, which is the case for the
  hybrid.
- Rehearsing more families did not help overall. Hybrid+ trained on all
  ten scores 0.459 on the ten; trained on the four rehearsal families it
  scored 0.478 on the same ten and seeds. Adding families the forest cannot
  separate appears to cost it accuracy on the ones it can. This is one
  comparison, not a designed test, and should be reported as an observation.
- Consistent with VeReMi (section above): withholding one attack type
  costs the forest little there too (0.779 → 0.735), while withholding a
  whole category costs a fifth (0.615). A leave-one-category-out run on our
  own families is the matching test and is queued.
- Hybrid+ remains the best detector in this protocol as well, seen and
  unseen, except on SUMO, where LOF alone is best (0.454 vs 0.431).

## pNEUMA field-coupling check (completed 2026-10-14, seeds 4-13)

In the pNEUMA converter, occupancy is computed from the vehicle's own
speed (occupancy_from_speed), so the two falsified fields are tied by a
rule on that source, and the value-bias attacks break it. If detectors
relied on that rule, the pNEUMA results would be inflated. Check: the same
speed goals with occupancy recomputed from the falsified speed by the same
rule (congestion_coupled, clear_road_coupled in iot_sim/adversary.py;
never used in training). scripts/run_coupled_check.sh, output
results/ml/coupled-check-pneuma.json.

| Detector | congestion, breaks rule | congestion, keeps rule | clear-road, breaks rule | clear-road, keeps rule |
|---|---|---|---|---|
| hybrid+ | 0.652 | 0.641 | 0.605 | 0.585 |
| forest+ | 0.640 | 0.630 | 0.549 | 0.566 |
| hybrid | 0.611 | 0.602 | 0.525 | 0.568 |
| plausibility + kNN | 0.640 | 0.636 | 0.643 | 0.650 |

Mean worst-case F1, 10 seeds. Keeping the rule lowers congestion-spoof
detection by 0.005-0.011 (consistent, p = 0.002) and changes clear-road
detection by −0.020 to +0.043 (not significant, p ≥ 0.08).

- The derived-occupancy artefact does not drive the pNEUMA results.
  Detection is essentially unchanged when the attack respects the rule,
  even though the detectors were trained only on rule-breaking examples.
  They detect these attacks through the speed change itself (its size, the
  implied acceleration and the gap to nearby vehicles), not through the
  speed-occupancy relation.
- The derivation must still be stated in the manuscript's data section,
  with this check as the evidence that it does not matter.

## Leave-one-category-out (completed 2026-10-14, seeds 4-13)

integration/leave_one_out.py --by-category (output
results/ml/leave-category-out-<source>.json, driver
scripts/run_leave_category_out.sh). The matching test to VeReMi's "unseen
category": when a family is scored, its whole category is withheld from
training, so no sibling family helps. Categories, by what is manipulated:
value (congestion spoof, clear-road spoof, drift, noise injection), stale
(replay, stuck-at), time (time shift, backdate), position, identity. Same
protocol as leave-one-family-out; 30 units.

| Detector | seen | one family withheld | its category withheld | seen → category |
|---|---|---|---|---|
| hybrid+ | 0.459 | 0.446 | 0.418 | −0.041 (−9%) |
| forest+ | 0.449 | 0.435 | 0.398 | −0.051 (−11%) |
| hybrid | 0.437 | 0.420 | 0.388 | −0.049 (−11%) |
| supervised forest | 0.426 | 0.406 | 0.366 | −0.060 (−14%) |
| LOF (no attack data) | 0.339 | 0.339 | 0.339 | 0 |

By category, seen → category withheld:

| Category | forest | forest+ | hybrid+ | LOF |
|---|---|---|---|---|
| value (4 families) | 0.482 → 0.376 | 0.527 → 0.428 | 0.511 → 0.434 | 0.259 |
| stale (2) | 0.394 → 0.330 | 0.462 → 0.417 | 0.460 → 0.414 | 0.264 |
| time (2) | 0.357 → 0.332 | 0.342 → 0.329 | 0.378 → 0.393 | 0.424 |
| position (1) | 0.418 → 0.404 | 0.394 → 0.381 | 0.439 → 0.427 | 0.533 |
| identity (1) | 0.412 → 0.429 | 0.385 → 0.395 | 0.428 → 0.399 | 0.447 |

By source, seen or family withheld or category withheld: SUMO forest 0.363 /
0.369 / 0.335, hybrid+ 0.423 / 0.431 / 0.425 (LOF 0.454); NGSIM forest
0.428 / 0.381 / 0.327, hybrid+ 0.436 / 0.394 / 0.334 (LOF 0.183); pNEUMA
forest 0.486 / 0.468 / 0.436, hybrid+ 0.517 / 0.512 / 0.493 (LOF 0.381).

Paired, category withheld (30 units): hybrid+ − forest +0.051 (27/30,
p = 3.5e-08); − hybrid +0.029 (30/30, p = 1.9e-09); − forest+ +0.019
(21/30, p = 8.9e-05); − LOF +0.078 (20/30, p = 9.9e-05). Forest seen −
category withheld +0.060 (p = 5.6e-09); hybrid+ +0.041 (p = 1.2e-05).

- The cost of an unseen mechanism is real; the cost of an unseen variant
  is small. Withholding one family costs the forest 5%; withholding its
  whole category costs 14%, and 22% on the value-manipulation category
  (0.482 → 0.376). VeReMi shows the same pattern (forest −6% for one type,
  −21% for a category).
- Plausibility features and the unsupervised part both shrink that
  cost, and together most: hybrid+ loses 9%. On the categories the
  supervised parts cannot expose (time, position, identity) LOF is the best
  single detector, rehearsed or not.
- NGSIM is the hard case. There LOF is weak (0.183), so the hybrid has
  little to fall back on, and hybrid+ loses as much as the forest. On SUMO
  and pNEUMA hybrid+ barely moves.
- This is the claim the paper can make in place of the earlier "about
  30% on novel families": supervised detectors transfer to new variants of
  a rehearsed mechanism, lose 14-21% on an unrehearsed mechanism, and a
  plausibility-plus-unsupervised hybrid cuts that loss to about 9% (our
  data) or 5% (VeReMi, 0.796 → 0.756).

## Operator-level and stress tests with Hybrid+ (completed 2026-10-15, seeds 4-8)

scripts/run_hybrid_plus_followups.sh (outputs results/ml/plus-*.json);
the same runs as the hybrid follow-ups above, with Hybrid+ added. The
forest, LOF and hybrid numbers reproduce the earlier runs exactly.

| Link | forest FPR or F1 | LOF FPR or F1 | hybrid FPR or F1 | Hybrid+ FPR or F1 |
|---|---|---|---|---|
| hrllc | 0.056 / 0.451 | 0.069 / 0.373 | 0.061 / 0.479 | 0.061 / 0.502 |
| lossy | 0.059 / 0.449 | 0.084 / 0.370 | 0.074 / 0.471 | 0.075 / 0.493 |
| degraded | 0.131 / 0.401 | 0.410 / 0.299 | 0.367 / 0.342 | 0.373 / 0.348 |
| severe | 0.251 / 0.346 | 0.763 / 0.269 | 0.687 / 0.286 | 0.700 / 0.286 |

| Poison rate | forest | LOF | hybrid | Hybrid+ |
|---|---|---|---|---|
| 0 | 0.452 | 0.373 | 0.479 | 0.503 |
| 5% | 0.491 | 0.340 | 0.469 | 0.480 |
| 10% | 0.399 | 0.326 | 0.412 | 0.418 |

Episodes (5% budget, every flag): detection 0.94 / 0.91 / 0.96 / 0.97 and
median delay 0.8 / 1.0 / 0.7 / 0.7 s for forest or LOF or hybrid or Hybrid+.
Alarm trade-off, best detection at about one false alarm per vehicle-hour
or less: forest 1% 3-of-5 0.64 (1.44 FA/vh, 5.3 s); Hybrid+ 0.5% 3-of-5
0.60 (0.58 FA/vh, 6.5 s); hybrid 0.5% 3-of-5 0.58 (0.55 FA/vh, 6.0 s).

- Hybrid+ is best on good links and under poisoning at 10%, as the hybrid
  was, and adds about 0.02 F1 throughout.
- It shares the hybrid's network fragility: the plausibility features do
  not reduce LOF's false alarms on degraded links.
- At the operating point an operator would use, Hybrid+ and the forest are
  within a few points of each other; the hybrid's advantage remains
  confined to permissive budgets.

## Difficulty-novelty confound, numbers (2026-10-18)

From results/ml/leave-one-out-*.json (30 units). Forest: four rehearsal
families, trained on all ten, 0.476; novel set A families trained on all
ten 0.354, each withheld 0.338. Apparent loss (rehearsal seen vs A
withheld) −29%; matched loss (A seen vs A withheld) −4%, Wilcoxon
p = 1.9e-09. Hybrid+: 0.511 / 0.401 / 0.389, apparent −24%, matched −3%,
p = 3.7e-09. Reported in the manuscript as the third evaluation pitfall.

## Rehearsal composition: does rehearsing more families help? (completed 2026-10-18, seeds 4-13)

scripts/run_rehearsal_composition.sh (outputs
results/ml/composition-plus-{hard,easy}-<source>.json; hybrid_plus
--train-families). Hybrid+ and its plausibility forest trained on the four
rehearsal families alone (hybrid-plus-*.json), plus two families the
message features expose well (noise injection, stuck-at: "easy"), plus four
they expose poorly (time shift, backdate, position, identity: "hard"), or
on all ten (leave-one-out "seen"); scored on all ten, worst case,
replacement model, 30 units. The easy/hard split was taken from the
leave-one-out "seen" scores, i.e. chosen after seeing them.

| Hybrid+ trained on | rehearsal (4) | easy (2) | hard (4) | all ten |
|---|---|---|---|---|
| 4 rehearsal | 0.542 | 0.480 | 0.413 | 0.478 |
| 4 + 2 easy | 0.533 | 0.491 | 0.405 | 0.474 |
| 4 + 4 hard | 0.505 | 0.442 | 0.395 | 0.449 |
| all 10 | 0.511 | 0.460 | 0.406 | 0.459 |

| Forest+ trained on | rehearsal (4) | easy (2) | hard (4) | all ten |
|---|---|---|---|---|
| 4 rehearsal | 0.532 | 0.479 | 0.382 | 0.461 |
| 4 + 2 easy | 0.536 | 0.499 | 0.361 | 0.459 |
| 4 + 4 hard | 0.514 | 0.443 | 0.352 | 0.435 |
| all 10 | 0.522 | 0.471 | 0.366 | 0.449 |

Paired against the four-family model (Hybrid+): adding the hard families
lowers the rehearsal families by 0.037 (0/30 units better, p = 1.9e-09)
and all ten by 0.030 (p = 3.1e-04), and does not improve the hard families
themselves (−0.018, p = 0.12). Adding the easy families costs 0.009 on the
rehearsal families (p = 2.1e-05) and improves the easy ones (+0.011).

- Rehearsing families the features cannot separate hurts. It costs about
  four points on the families the detector could already catch, and buys
  nothing on the added ones.
- Rehearsing separable families helps a little where it should (on the
  added families) at a small cost elsewhere.
- A plausible mechanism, not tested directly: attack examples that look
  benign push up the forest's probabilities for benign messages, so the
  out-of-bag threshold at the 5% budget rises and recall falls on the
  separable families.
- Practical rule: build the rehearsal library from manipulations the
  feature set can expose; leave the others to the unsupervised part.
