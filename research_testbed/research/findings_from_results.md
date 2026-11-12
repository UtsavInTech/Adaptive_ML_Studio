# Findings from the saved results

**What this is.** An analysis of the runs already in `results/experiments/` (11 November 2026), written to find where the joint controller loses and which improvements are worth building. One offline exploratory test was added (Q2, marked). Nothing in the testbed or the engine was changed.

**How far to trust it.**
- Most settings have **one seed**. Several runs shared the machine with two long ensemble runs, and the controller reacts to *measured* time. Its decisions therefore change from run to run (see Q6).
- Cost figures in µs vary by up to 2× for the same configuration, depending on machine load. Read shares, not absolute µs.
- Every "estimated gain" below is a rough bound derived from saved runs, not a measurement of the improved system.

**Scripts** are in `research/scripts/`: `common.py`, `error_structure.py`, `cost_terms.py`, `oracle_switch.py`, `periods_delay.py`, `post_adapt.py`, `label_free_easy.py`, `feature_choice.py`, `figures.py`. Run them with `backend/.venv/bin/python` and set `ANALYSIS_CACHE` to a scratch folder. **Figures** are in `research/figures/`.

| Short name | Run id | Rows |
|---|---|---|
| p2 core (no_change, static, incremental, adaptive, ARF) | `20261111-145934-568975-experiment-phase-2-core-methods-on-cic-ids2017` | full stream, seed 42 |
| p2 SRP / LevBag | `20261111-145938-211780-…srp…`, `20261111-145941-337166-…levbag…` | full, s42 |
| p3 (adaptive and joint, standard and gateway) | `20261111-165347-608995-experiment-phase-3-adaptive-vs-joint-standard-and-g` | full, s42 |
| p3 ablations (no gating, no R2, no R3, no R5) | `…171732-036467…`, `…172314-227666…`, `…172824-164084…`, `…174022-182362…` | full, s42 |
| memory with / without R5 | `20261111-194052-088567-…-memory-full`, `20261111-195427-125877-…-memory-without-r5` | full, s11/23/37 (identical) |
| quick protocol (core, ensembles, ablations, labels, rates) | the 20 ids in `protocol/generated-quick/runs.txt` | Wednesday 693,702 + 300k, s11 |

## Q1. Where is quality lost?

**Finding.**
- Errors happen where the true label switches, **inside attack periods**. For the joint controller (standard tier, full stream), 86 % of its errors fall within 100 rows of a label change. 91 % of its false alarms are benign flows *inside* the scheduled attack time ranges, which are interleaved with attack flows. Outside those ranges, it raises 288 false alarms in about 1.2 M benign rows.
- Loss at the **onset of an attack** is the second source. Over 58 onsets (an attack after ≥1,000 benign rows), joint misses 54 % of the first 100 attack flows (1,257 of 2,315). ARF and repeat-last-label each miss about 19 %.
- Loss at attack ends (false alarms in the 5,000 benign rows after an episode) is small: 15 % of joint's false alarms.

**Why joint is slow at onset.** When resources are spare, joint follows R1: a replacement model trains in the background and is swapped in after `background_min_samples = 200` rows. On the big new-attack periods, joint's flows-before-first-flag are 192–215 (Infiltration-Portscan, Portscan), 126 (DDoS) and 161 (GoldenEye), which is that 200-row wait. With an immediate reset (the gateway run without R3, which stays in lightweight mode), the same periods take 12–22 flows. ARF takes 3–14.

Joint also adapts repeatedly *within* long stable attacks. During DoS Hulk (158k flows), the drift detector fires 49 times and the model is replaced 41 times, and joint misses 1,033 Hulk flows. ARF has no detector events there and misses 85. Infiltration-Portscan shows the same: 57 replacements and 2,468 missed flows, against 640 for ARF.

| Full stream, after warm-up | Errors | Within 100 rows of a label switch | Missed of first 100 flows per onset | False alarms inside attack ranges | Σ flows before first flag |
|---|--:|--:|--:|--:|--:|
| Repeat last label | 27,210 | 100 % | 18 % | 99.9 % | — |
| Adaptive (old controller) | 13,852 | 91 % | 33 % | 96 % | 386 |
| Joint, standard | 9,770 | 86 % | 54 % | 91 % | 1,309 |
| Joint, gateway (R3 active) | 52,698 | 84 % | 74 % | 98 % | 2,537 |
| Joint, gateway, without R3 | 6,541 | 87 % | 22 % | 92 % | 334 |
| ARF | 2,949 | 98 % | 19 % | 99 % | 265 |
| SRP | 2,196 | 94 % | 19 % | 97 % | — |

Missed attack flows by type, joint standard: Infiltration-Portscan 2,863 (44 % of its misses), DoS Hulk 1,033, Portscan 848, DDoS 381, GoldenEye 319. The tiny classes (Heartbleed 11, Web attacks 104, Infiltration 36 flows) are missed by **every** method. Figure: `figures/q1_error_position.png`.

**So what.**
- The detector-and-replace loop is the weak part, not the learner:
  - it waits 200 rows at every new attack;
  - it churns during long stable attacks.
- Two cheap fixes follow:
  - Use the replacement for prediction as soon as it beats the active model on recent rows, or reset immediately when a new attack starts.
  - Damp re-alarms after a replacement, for example with a longer cooldown while the label mix is stable.

## Q2. R3's collapse under tight CPU

**Finding: the feature cut is a bug in timing, not a hard trade-off.**

In the full-stream gateway run, R3 halved the features at rows 1,019, 1,519, 2,581 and 3,635: from 56 to 28, 14, 7 and then **4**. Stride went to 2 at row 12,489 and to 4 at row 15,401. The model kept those 4 features for the remaining 2.1 M rows. R3 never stepped back up.

The four kept features were `Dst Port, Flow Packets/s, Fwd Packets/s, FIN Flag Count`. They were chosen from a ranking that was **frozen at row 1,019**. Narrowing freezes the ranking (`pipeline._learn`: `if not self.narrow: selector.learn`), and R3 fired 19 rows after warm-up. By then the ranker had seen 1,019 Monday rows, all benign. Its weights reflected input scale, not relevance.

- **Wednesday micro_sim** shows the same pattern. Its ranking froze at row 1,019, and it ended on `Flow Bytes/s, Fwd Bulk Rate Avg`. `Fwd Bulk Rate Avg` has univariate AUC 0.48–0.49 on both Tuesday and Wednesday, so it carries no information, yet it was the benign-only ranker's top feature.
- **What happened to quality.** Recall fell and false alarms rose, mainly within attack periods:
  - FTP-Patator recall 99 → 59 %, Slowloris 93 → 43 %, Infiltration-Portscan (first) 80 → 33 %;
  - Slowloris-Attempted flagged 0.2 → 28.6 %;
  - benign false alarms 0.2 → 1.5 %.

  Errors per 10,000-row block were 5–10× those without R3 in every attack stretch. Quiet benign stretches were error-free for all methods (`figures/q2_gateway_blocks.png`).

**Exploratory test** (`scripts/feature_choice.py`):
- Data: Wednesday's 300k rows.
- Model: a plain Hoeffding tree (grace 200) on fixed feature sets, learning every row, with no detector.
- Rankings: chosen only from Tuesday's labelled data, plus a hindsight reference.
- About 6 minutes of compute.

| Feature set | k | Errors | Recall | False alarms | κ-temporal | Tree µs/row |
|---|--:|--:|--:|--:|--:|--:|
| R3's micro_sim end state (`Flow Bytes/s, Fwd Bulk Rate Avg`) | 2 | 18,112 | 96.2 % | 9.0 % | −1.39 | 16 |
| R3's full-stream 4 (frozen, benign-only ranking) | 4 | 5,876 | 98.3 % | 2.3 % | 0.22 | 16 |
| Univariate AUC on Tuesday, top 4 | 4 | 4,899 | 98.2 % | 1.4 % | 0.35 | 17 |
| The selector's own LR fed Tuesday labels, top 4 | 4 | 4,371 | 99.1 % | 2.2 % | 0.42 | 18 |
| R3's micro_sim 7 | 7 | 4,301 | 99.1 % | 2.2 % | 0.43 | 21 |
| All 83 inputs | 83 | 4,228 | 98.6 % | 1.4 % | 0.44 | 133 |
| Hindsight: AUC on Wednesday, top 4 | 4 | 3,820 | 99.1 % | 1.8 % | 0.50 | 16 |
| **The selector's LR fed Tuesday labels, top 8** | 8 | **3,207** | 99.1 % | 1.3 % | **0.58** | 22 |

Same story on the full stream:
- **Memory tier with R5:** the ranking keeps learning (not narrowed), and R5's fresh models re-select the top 14 from the *current* ranking. Result: 11,578 errors at 108 µs/row.
- **Gateway run with R3 active:** 52,698 errors at 40 µs/row.
- So a 14-feature configuration with a live ranking came within about 8 % of the gateway's 100 µs budget, with 4.5× fewer errors. (The two runs ran under different machine load.)

**So what.**
- Do not freeze the ranking at R3's first step. Keep updating it on a sample of rows, or rank on labelled data that contains both classes.
- Set a floor of about 8 features. Going to 2 is catastrophic. Eight well-ranked features match or beat all 83 for this learner at a sixth of the tree cost.
- Cut features only after the ranking has seen attacks. Until then, cut cost elsewhere (Q3).

## Q3. Cost structure: a direct answer to §4.3's open question

The paper says which stage dominates end-to-end latency "remains an open question" (§4.3, Table 3 "Stage Bottleneck Attribution"). On this stream (83 inputs, Python/River, 8 GB Apple Silicon), the measured answer is:

> **Two stages take 75–85 % of the time in every learning configuration: preprocessing (C_pre) and the incremental model update (C_upd).** Feature selection takes 7–12 % while its ranking is updated over all inputs, and 1–2 % once frozen. Drift detection never exceeds 8 % (≤ 6 µs/row). Retraining (C_ret) is 0–5 %, and the controller's own decisions are 1–13 %. Without learning (static, repeat-last-label), preprocessing alone is 80 %. Reducing the feature set saves almost nothing unless preprocessing is narrowed with it. The memory tier's model uses 14 features, but it still preprocesses all 83 inputs, and C_pre stays at 52 % (55 µs).

| Configuration (run) | C_pre | C_fs | C_inf | C_drift | C_upd | C_ret | C_ctrl | Total µs/row |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Repeat last label (Wed, q core) | 81 % | 18 % | 0 % | 0 | 0 | 0 | 0 | 161 |
| Static (Wed) | 80 % | 7 % | 12 % | 0 | 0 | 0 | 0 | 55 |
| Adaptive, old controller (full, p3) | 65 % | 12 % | 5 % | 2 % | 10 % | 0 % | 4 % | 111 |
| Incremental (Wed) | 37 % | 9 % | 8 % | 0 | 45 % | 0 | 0 | 352 |
| Joint, standard (full, p3) | 37 % | 8 % | 9 % | 1 % | 40 % | 2 % | 1 % | 209 |
| Joint, gateway without R3 (full) | 35 % | 8 % | 8 % | 1 % | 44 % | 0 % | 2 % | 298 |
| Joint, memory tier with R5 (full, 14 features, not narrowed) | 52 % | 11 % | 5 % | 1 % | 25 % | 1 % | 3 % | 108 |
| Joint, small_sim (Wed, narrowed) | 25 % | 1 % | 17 % | 2 % | 50 % | 0 % | 3 % | 227 |
| Joint, gateway (full, 4 features, narrowed, stride 4) | 26 % | 2 % | 25 % | 7 % | 19 % | 3 % | 12 % | 40 |
| ARF (Wed) | 12 % | 3 % | 12 % | 0 | 74 % | 0 | 0 | 1,271 |

Per tier: in standard and small_sim, update first and preprocessing second. In micro and gateway, once narrowed, the remaining cost is spread out (update 19–39 %, inference 19–25 %, preprocessing 22–26 %, controller 9–12 %). All the cost rows come from `scripts/cost_terms.py`. Figure: `figures/q3_cost_terms.png`.

**Two further measurements:**
- **Updating the scaler's statistics** is about two thirds of C_pre. On the same Wednesday rows, static (transform only) spends 44 µs and repeat-last-label (transform and update) spends 130 µs.
- **C_pre scales with the number of inputs processed.** In the same batch, 83 inputs cost 147 µs, 28 cost 56 µs and 2–3 cost 15 µs.

**Savings estimates** for joint standard (full stream, 209 µs/row). Shares come from the table; the scaling assumptions are stated for each.

| Change | Estimated saving | How estimated | Quality risk |
|---|--:|---|---|
| (a) Preprocess only the 56 model features from the start, and update scaler statistics every 4th row (fading factor ×4) | ~50 µs (−24 %) | C_pre 77 µs × 27/83 ≈ 25; then ⅔ (statistics) × ¾ of the rest ≈ 26 | Low. The model never sees the other 27 inputs. Ranking them needs (c). |
| (b) Skip the model update on rows where the last 100 labels agree and the model was right on all of them | ~64 µs (−31 %) | C_upd 83 µs × 77 % of rows that qualify. Those rows hold 7.6 % of errors, at an error rate of 0.05 %. | Probably low. Learning from a random 10 % of rows kept joint at κt 0.63, against 0.57 at 100 % (Wed labels delay0 cov0.1 vs cov1). Targeted skipping is untested. |
| (c) Update the selector's ranking on 1 row in 10 | ~15 µs (−7 %) | fs-learn ≈ 17.6 µs × 0.9 | Low. Also fixes Q2's frozen ranking. |
| **All three** | **~209 → ~80 µs** | sum of the above | Would put 56 features inside the gateway's 100 µs budget without R3 cutting features. The same scaling puts the contended 298 µs gateway-without-R3 run at about 115 µs. |

**So what.**
- R3's first lever should be "cheaper per row" (a, b, c), not "fewer features".
- Feature cuts belong at the end of the ladder, with the ranking fix from Q2.
- This also gives Table 3's "Update and Retraining Overhead" gap a measured number: the update is 40–50 % of a learning pipeline's time, and retraining is under 5 %.

## Q4. Label delay (1,000 and 10,000 rows)

**Finding: the failure is mostly self-inflicted resets, not stale models at onset.**
- **Joint, delay 1,000:** 58,252 errors, against 9,602 for plain incremental, which has no detector and no resets.
- **Drift alarms and resets:**
  - the detector fires 484 times (73 with no delay), and joint resets the model 221 times (R2 lightweight on small_sim);
  - after each reset, the new model is blind for D rows, because its first labels arrive D rows later;
  - **84 % of joint's errors fall within 1,000 rows after one of its own resets** (27 % error rate there, against 7.7 % elsewhere).
- **Onset windows** (each onset to onset + delay + 2,000 rows) hold only 11 % of joint's errors, and attack-end windows hold 4 %.
- **Old adaptive controller:** 79 % of its errors fall after a replacement.
- **Fewer labels can help.** At delay 1,000, 10 % coverage cut joint's errors to 20,000, because there were fewer alarms (37).

| Wed 300k, small_sim | Errors | Recall | False alarms | Drift alarms | Replacements | Errors ≤D rows after a replacement | Errors in onset windows |
|---|--:|--:|--:|--:|--:|--:|--:|
| Joint, delay 0 | 3,250 | 98.9 % | 1.0 % | 73 | 69 | 15 % (500-row window) | 13 % |
| Joint, delay 1,000 | 58,252 | 73.2 % | 10.0 % | 484 | 222 | **84 %** | 11 % |
| Joint, delay 1,000, 10 % labels | 20,000 | 92.1 % | 4.9 % | 37 | 26 | 26 % | 26 % |
| Joint, delay 10,000 | 75,853 | 63.9 % | 10.6 % | 421 | 182 | 98 % (window covers 83 % of rows) | 36 % |
| Incremental, delay 1,000 | 9,602 | 95.5 % | 1.5 % | — | 0 | — | 45 % |
| Incremental, delay 10,000 | 28,069 | 84.1 % | 0.6 % | — | 0 | — | 66 % |
| Adaptive, delay 1,000 | 66,142 | 68.3 % | 8.7 % | 556 | 307 | 79 % | 10 % |

**Upper bound for a perfect "attack started" signal at onset.** At most, it recovers the errors in the onset windows:
- joint, delay 1,000: about 6,600 of 58,252 (11 %);
- incremental: 4,300 of 9,602 (45 %) at delay 1,000, and 18,600 of 28,069 (66 %) at delay 10,000.

So an onset signal is worth having only *after* the reset problem is fixed. Figure: `figures/q4_label_delay.png`.

**So what.** Make adaptation aware of the label delay:
- A replacement must not discard the old model until it has D labelled rows. Warm-start it from the R4 buffer, and keep predicting with the old model meanwhile.
- Freeze the detector for D rows after an adaptation. The errors arriving then are the old model's errors.

Bound: joint at delay 1,000 should reach incremental's ~9.6k errors (−83 %) or better.

## Q5. Uncertainty and easy rows: sizing a cascade

**Finding: most rows are easy and nearly error-free.**

*Label-based test:* the last 100 labels agree and the model was right on all of them.
- On the full stream, 77 % of joint's rows qualify. Its error rate there is 0.05 %, and those rows hold 7.6 % of its errors. Elsewhere the error rate is 1.8 %.
- On Wednesday: 57 % of rows, an error rate of 0.13 %, and 8 % of errors.
- Copying the previous label on those rows would err 0.12 % of the time, about the same as the model.

*Label-free test (usable under delay):* the model's own last 100 predictions agree.
- 79 % of rows qualify, but they hold 48 % of joint's errors. The error rate there is 0.28 %, against 1.17 % on the other rows.
- This test is a weaker signal.

| Full stream | Easy share (labels, k=100) | Error rate easy / hard | Errors on easy rows | Easy share (own predictions, k=100) | Errors on those rows |
|---|--:|--:|--:|--:|--:|
| Joint, standard | 77 % | 0.05 % / 1.8 % | 7.6 % | 79 % | 48 % |
| ARF | 78 % | 0.04 % / 0.49 % | 24 % | 81 % | 45 % |
| Joint, gateway | 76 % | 0.08 % / 10 % | 2.4 % | — | — |

Today, easy rows cost the same as hard ones: joint standard spends 195 µs on easy rows against 209 µs on average.

**So what.**
- A cascade pays off on the **update path**. Skipping updates on correct, easy rows saves about 31 %; that is Q3(b). The label is in hand when the update runs, so the label-based test is valid even under delay.
- A cheap **inference path** gives little. Inference is only 5–17 % of the time, and the label-free test is too leaky (48 % of errors) to send rows to a weaker model.

## §6.3 configuration search: the oracle-switch upper bound

**Method** (`scripts/oracle_switch.py`):
- Each saved run is treated as a fixed configuration θ (features, narrowing, stride, rules, model).
- For each 10,000-row block, the oracle picks the run with the fewest errors whose mean measured service time in that block meets the tier's CPU budget.
- A second version needs to meet the budget only on average over the stream. That is the minimiser of J = errors + λ·C, with λ set so the mean cost equals the budget, i.e. §6.3 with α and γ only.

**Read it as a loose upper bound.**
- Switching is assumed free.
- Each run's errors in a block assume its own model history.
- Which blocks "meet the budget" depends on machine load.
- The candidate set is only the runs that happen to exist.

| Setting | Rules as run | Oracle, budget met in every block | Oracle, budget met on average |
|---|--:|--:|--:|
| Full stream, gateway (100 µs), 10 joint/adaptive configurations | 52,695 errors at 40 µs | 38,426 (−27 %) at 42 µs | 5,315 (−90 %) at 99 µs |
| Full stream, gateway, also baselines and ARF | 52,695 | 19,874 (−62 %) at 53 µs, using repeat-last-label in 53 blocks | 3,159 (−94 %) at 99 µs |
| Wed, small_sim (100 µs), 23 joint configurations | 2,604 at 231 µs (budget missed) | 2,424 at 87 µs (budget met) | 1,127 (−57 %) at 100 µs |
| Wed, micro_sim (50 µs), 23 joint configurations | 7,813 at 73 µs | 6,949. Nothing met the budget in 16 of 29 blocks. | 7,707 |

**What the oracle picks.** It runs cheap configurations in quiet benign blocks, which are error-free for every configuration. It spends the budget on rich configurations (56 or 14 features) during attack stretches.

- Under the per-block budget, most of the gain comes from avoiding the gateway run's worst blocks. That gain is mostly Q2's bad feature choice, not configuration search as such.
- The average-budget figure (−90 %) is the real prize. On this stream, spending is worth timing, because errors cluster in about 40 % of the blocks.
- The micro_sim budget was not reachable by any saved configuration under the load at the time. Its bound is therefore uninformative.

**So what.** A simple two-mode θ policy could capture part of this:
- rich configuration when the recent label-switch rate or the drift detector says an attack is active;
- cheap configuration otherwise;
- a credit budget enforcing the mean.

How much of the −90 % it captures is unknown. The free-switching assumption is the main optimism.

## Q6. What a reviewer would raise (and what helps)

1. **The ablations are inside the noise.**
   - micro_sim "core" against "without R5": R5 never fired in either run. Yet R3 made 5 cuts (to 2 features, κt −0.03) in one and 2 cuts (to 14 features, κt 0.58) in the other. The only difference is measured time.
   - The same small_sim configuration, run twice (q core and q labels delay0 cov1), gave κt 0.65 and 0.57.
   - **Use a deterministic cost model** (simulated per-stage cost from feature count and model size) for the controller's decisions, and report measured time separately. Otherwise, use ≥5 seeds and `--workers 1`.
2. **Shortcut features.**
   - `Dst Port` has univariate AUC 0.003 on Tuesday: it alone separates FTP/SSH-Patator from benign. It is in the gateway's 4 features.
   - The top Tuesday features for the selector are TCP fingerprints of the attack tool: `Fwd Seg Size Min`, `SYN Flag Count`, `Down/Up Ratio`. `FWD Init Win Bytes` is also ranked high by AUC.
   - Report an ablation without port and window and segment-size fields.
3. **Label persistence.** Repeat-last-label scores 98.70 %, and 84–100 % of all methods' errors are within 100 rows of a label switch. Every method's κ-temporal is negative at delay ≥1,000. The delay-0 numbers are optimistic, and the paper should lead with the delayed-label results.
4. **The false-alarm rate measures interleaving, not quiet traffic.** 91–99 % of false alarms fall inside attack time ranges, and "Attempted" flows count as benign. The gateway run flags 75 % of GoldenEye-Attempted and 29 % of Slowloris-Attempted. Report false alarms inside and outside attack periods separately.
5. **Quality ceiling and baselines.**
   - ARF has 3.3× fewer errors than joint standard, at 3–6× the cost.
   - On Wednesday, plain incremental (2,472 errors) beats joint small_sim (2,625) and joint standard (3,239). Its time, 352 µs, is 1.5× joint small_sim's.
   - The controller's demonstrable value is **meeting budgets**, not quality. Frame it that way.
6. **Unmeasurable classes.** Heartbleed (11 flows), Web attacks (104) and Infiltration (36) score 0 % for every method. Say so, or merge them; do not average them in.
7. **One lab, one week, one seed** for most settings. The second dataset (PLAN.md §2) is needed for any generality claim.
8. **What strengthens the story.**
   - The stage-cost decomposition is clean: the terms sum to the measured time within a few µs.
   - It answers the paper's open question directly (Q3).
   - The memory-tier result is deterministic across 3 seeds.
   - R2's lightweight reset beats R1's background replacement at attack onsets (Q1), which is a concrete, testable rule-ordering finding.

## Ranked improvements

| # | Improvement | Estimated gain (and how estimated) | Experiment to confirm |
|--:|---|---|---|
| 1 | **Fix R3's feature choice.** Keep the ranking learning (sampled) while narrowed. Do not cut before the ranker has seen both classes. Floor at 8 features. | Gateway, full stream: from 52.7k toward ~11.6k errors (−75 %). Estimated from the memory tier's live-ranking 14-feature run at 108 µs. Offline on Wednesday: κt 0.22 → 0.58 (frozen 4 → selector's top 8). Micro's 2-feature end state: κt −1.39 → ≥ 0.43. | Gateway full stream and Wednesday micro_sim, 3 seeds, `--workers 1`, before and after. |
| 2 | **Delay-aware adaptation.** Warm-start replacements from the labelled buffer, keep the old model until the new one has D labels, and mute the detector for D rows after an adaptation. | Joint at delay 1,000: 58k → ≤ ~10k errors (−83 %). Bound: incremental, which never resets, gets 9.6k, and 84 % of joint's errors follow its own resets. | Wednesday labels grid (delays 1,000 and 10,000, coverage 1 and 0.1), joint against incremental. |
| 3 | **Cheaper per row before fewer features.** Narrow preprocessing to the model's features from the start, update scaler statistics every 4th row, rank 1 row in 10, and skip updates on easy correct rows. | 209 → ~80 µs/row at 56 features (−60 %). Estimated term by term from the cost shares (Q3). This meets the 100 µs gateway budget without feature cuts, i.e. gateway at about the quality of the run without R3 (6.5k errors, against 52.7k). | Implement as R3's first steps. Full-stream gateway and small_sim. Measure C_upd and C_pre and κt. |
| 4 | **Faster onset response.** On drift, predict with the replacement once it beats the active model on the last ~20 labelled rows, or reset immediately; damp re-alarms in long stable attacks. | Joint standard misses 54 % of the first 100 flows per onset, against 22 % for the immediate-reset run; about 740 fewer misses (−8 % of errors). Lightweight-only joint has 6.5k errors against 9.8k (−33 %), which bounds the total gain. | Full stream, standard tier, R1 variants, 3 seeds. Per-period flows-before-first-flag. |
| 5 | **Two-mode configuration policy (§6.3).** Rich θ during attack activity, cheap θ in quiet stretches, mean budget enforced by a credit. | Oracle bound: gateway −90 % errors (52.7k → 5.3k) at the same 99 µs mean. The real gain is likely a fraction of this because of switching costs. | Implement switching on the recent label-switch rate. Compare against the oracle on the full stream. |

Items 1 and 3 together address the gateway and micro collapse. Item 2 is the largest effect for any realistic deployment, where labels arrive late. All five estimates come from one seed and loaded machines, so treat them as orders of magnitude.
