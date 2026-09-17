# Running experiments

This is the research workstream's guide to the platform: how to define a run, what it produces, and
which rules keep the measurements valid. **The platform measures and records; it never concludes.**

## 1. Two ways to run

| Mode | What it is | Use it for |
|---|---|---|
| **Live** | One trial, paced at a stream rate, with every method in one process; streamed to the UI | Watching the story, the demo, injecting drift by hand |
| **Experiment** | One trial per method × profile × rate × seed, each alone in a fresh process, run one after another | **Every number that goes in the report** |

Live and experiment runs are mutually exclusive: the API refuses to start one while the other is
running, because sharing the CPU would invalidate both sets of timings.

Per-sample timings during a paced live run are several times higher than at max speed (cold caches,
lower clock). See `docs/performance.md` — another reason the figures of record come from Experiment mode.

## 2. Defining an experiment

```yaml
name: "Compare methods — validated scenario"
base:                      # a TrialConfig: the stream, the methods, the pipeline, the evaluation
  seed: 42
  methods: [static, incremental, adaptive, arf]
  stream: {length: 16000, noise: 0.05, drifts: [{position: 10000, to_variant: 3}]}
profiles: [standard, edge_sim]     # names or full profile objects
rates: [null, 1000]                # null = max speed; a number paces the stream
seeds: [42, 43]
```

Every combination becomes a trial with an id such as `adaptive__edge_sim__1000ps__s43`.

Run it:

```bash
cd backend
.venv/bin/python -m adaptiveml.experiments.run presets/experiments/compare_methods.yaml
```

or from the **Experiments** tab in the UI. Ready-made presets are in `backend/presets/experiments/`:
`compare_methods`, `standard_vs_edge`, `cross_scale`, `hard_scenario`.

### Things worth knowing before you design a sweep

- **The stream rate does not change predictions.** Drift is placed by sample index and every sample is
  processed, so rate only affects cost, response time and backlog — unless a resource budget makes the
  pipeline shed work, which is the point of the `cross_scale` preset.
- **Warm-up.** Every method trains on the first `evaluation.warmup` samples; metrics exclude them.
- **The first drift must come after the warm-up** (the config validator enforces it).
- **Detection strength depends on the scenario**: a longer stable period before the drift, lower label
  noise and a larger concept change all make detection more reliable (`results/sensitivity/…`).

## 3. What a run produces

```
results/experiments/<experiment_id>/
  manifest.json          status, environment, provenance, per-trial headline numbers, hashes
  config.resolved.yaml   the full configuration, defaults included
  trials/<trial_id>/
    summary.json         scores, latency percentiles, per-stage means, adaptations, stability references
    blocks.csv           one row per 100-sample block: confusion counts, per-stage times, model state
    engine_blocks.csv    CPU and wall time per block, backlog and response time for paced runs
    events.jsonl         drift, detection, adaptation, budget and configuration events
    outcomes.csv.gz      per sample: y_true, each method's prediction, service time
  resources.csv          1 Hz CPU/RSS of the engine process (live runs)
results/experiments/index.csv     one row per trial × method, across all runs
```

`outcomes.csv.gz` is the important one for the research workstream: it lets you recompute **any**
metric — including a different definition of accuracy stability — without re-running anything.

```python
import pandas as pd
outcomes = pd.read_csv("results/experiments/<id>/trials/<trial>/outcomes.csv.gz")
correct = (outcomes.y_true == outcomes.adaptive_pred)
rolling = correct.rolling(500).mean()          # windowed accuracy, any window you like
```

## 4. Reproducibility

- Same config + same seed ⇒ **bit-identical predictions**; the manifest stores a SHA-256 of each
  method's predictions.
- **Re-run and check reproducibility** (UI button, or `adaptiveml.experiments.rerun`) re-runs every
  trial in a fresh process at max speed and reports how many reproduced exactly.
- Timings are *not* expected to match; the environment (CPU, RAM, OS, power source) is recorded with
  every run.
- **Exception:** a trial under a measured-time budget (`edge_sim`) is *not* bit-reproducible, because the
  governor reacts to timing. Such trials are flagged `timing_dependent_behaviour` and their decisions
  are all in `events.jsonl`.

## 5. Rules that keep measurements valid

1. One run at a time; the API enforces it.
2. Experiment trials run **sequentially**, each in a fresh process.
3. Latency figures exclude monitoring, which is measured and reported separately.
4. Prefer several seeds and report the spread; the M1's performance/efficiency cores make single runs noisy.
5. Note the power source — the environment block records it (battery runs are slower).

## 6. Open decisions for the research workstream

These are deliberately **not** fixed in code (see `docs/architecture.md` §14):

- the definition of accuracy stability, the recovery criterion and the segment anchoring;
- the definition of computational overhead;
- the datasets (a real benchmark stream is still to be added) and the synthetic parameters;
- which comparators to report (ARF is implemented and cited [20]);
- the simulated edge budget values — the current ones are **placeholders**;
- the protocol: seeds, repetitions and the order of trials.
