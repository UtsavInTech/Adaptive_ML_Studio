# Local MVP stress validation

## Assessment of the existing project

The project partially met the requested specification before this harness was added.

| Requirement | Existing behavior | Harness addition |
| --- | --- | --- |
| Real static data, sequential learning | Kaggle ELEC2 and occupancy replay; test before train | Reuses catalog checksums, file order and real pipeline |
| C_pre, C_inf, C_upd | Native six-stage timing already existed | One CSV record per row, CPU%, signed RSS delta, adaptation costs included |
| Halfway data bomb | UI injection swaps feature columns | Persistent 10x scaling of selected inputs; exactly 200 randomly positioned label flips over 500 rows |
| Per-instance 15 ms response | Resource governor uses block averages | Immediate halving of active model dimensions, minimum one |
| Accuracy floor | No matching unified local policy runner | Rolling 500-row accuracy floor of 70%, with refresh cooldown |
| Local validation entry point | No stress_test_mvp.py | One script, control mode, intentional latency fault and durable reports |

The new default **project** engine calls the actual `MethodPipeline`. It overrides only its stress-run configuration: all features initially, immediate model replacement rather than background promotion, and a 500-row cooldown. It does not alter UI behavior or the application's production governor. The **standalone** engine embeds an online River baseline and can run outside this repository with an explicitly supplied CSV. Results from that engine do not validate the application's pipeline.

The request does not supply formal definitions of the paper's R1–R5 labels. This implementation explicitly proposes the following mapping; it does not claim these are verbatim paper rules:

- **R1:** increasing-error ADWIN detection triggers model replacement. If the native policy already replaced it, do not replace it twice. An improvement-only drift signal is logged without forcing a reset.
- **R2:** service time above 15 ms immediately halves active model inputs (`floor(n/2)`, retaining at least one), even during cooldown. One feature remaining yields an unresolved violation rather than a false recovery claim.
- **R3:** a full rolling window below 70% accuracy requests a model refresh.
- **R4:** 500 rows between accuracy-triggered refreshes prevent repeated resets; R1 and R2 can override this.
- **R5:** malformed/nonfinite data, processing failures and RSS growth above 512 MB abort the run. Partial results remain available after runtime failures or Ctrl-C.

Feature reduction changes the dimensions presented to the model. Preprocessing still handles the input columns. It is a recovery attempt, not a guarantee that the next row meets the deadline.

## macOS run guide

Use Python **3.11 or newer**. Work in a virtual environment; no system-wide installation or `sudo` is needed.

```bash
cd /Users/utsavsingh/Documents/Adaptive_ML_Studio
python3 --version
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e './backend[dev]'
```

If the existing `backend/.venv` is already installed, skip those installation steps. The script uses `psutil` and River (already declared by the backend), not pandas or scikit-learn. The project engine additionally uses the backend's declared dependencies.

Run a full clean control, then the same dataset with the default data bomb:

```bash
backend/.venv/bin/python stress_test_mvp.py --dataset elec2 --clean
backend/.venv/bin/python stress_test_mvp.py --dataset elec2
backend/.venv/bin/python stress_test_mvp.py --dataset occupancy --clean
backend/.venv/bin/python stress_test_mvp.py --dataset occupancy
```

These print every iteration. Add `--log-every 1000` for quieter output; every iteration is still saved. Run them sequentially and close heavy background applications for more useful timings. No server, GPU, Kaggle login, or network is required once the dataset snapshots are present. Catalog checksums are verified before learning. Missing snapshots must be prepared using the repository's existing dataset setup described in `data/README.md`.

Exercise the latency recovery branch deliberately with one 20 ms preprocessing delay at the midpoint:

```bash
backend/.venv/bin/python stress_test_mvp.py \
  --dataset elec2 --limit 3000 --warmup 500 \
  --fault-latency-ms 20 --log-every 500
```

This delay is explicitly recorded as `fault_ms`; it must not be presented as genuine model cost. The shortened warm-up is only for this smoke test. Full runs use catalog warm-ups (ELEC2 1000; occupancy 3000).

For a portable standalone run, copy the script and your CSV to any directory, create a virtual environment there, and use explicit numeric feature and binary-label columns:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'river==0.26.1' 'psutil>=6'
.venv/bin/python stress_test_mvp.py --engine standalone \
  --csv /absolute/path/to/data.csv \
  --features temperature,humidity,light --target occupied \
  --negative 0 --positive 1 --warmup 100
```

The CSV must have at least 1000 valid rows for the default 500-row noise window. The script validates/counts the file once using constant memory, then reopens it and predicts, detects, adapts and learns one row at a time. It never trains on a full array, shuffles rows or rewrites source data. Binary label values are explicit; other targets are rejected.

Run regression checks:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_stress_mvp.py -q
```

## Reading the output

Each invocation creates a unique directory under `results/stress/`:

- `iterations.csv`: zero-based row, elapsed timestamp, clean/observed labels, prediction, corruption flags, cost components, CPU, RAM, feature count, rolling accuracy and controller actions.
- `events.jsonl`: data-bomb, native detector/adaptation and controller events with observed elapsed milliseconds.
- `summary.json`: dataset checksum, configuration, phase accuracy against both clean and observed labels, deadline misses, costs and completion status.

`C_pre` measures preprocessing transforms. `C_inf` measures prediction. `C_upd` includes learning and adaptation, including controller-triggered model replacements. `C_other` covers selection and detection; `C_policy` is remaining controller overhead. Their sum is `C_total`. Detection/replacement event timestamps are recorded when the loop observes the event, not hardware-level interrupt timestamps.

CPU is process CPU time divided by monitored wall time, with one core equal to 100%. Short iterations may report zero or noisy percentages because OS counters have finite resolution. RAM is signed process RSS change in decimal MB; it can be flat or negative. CSV parsing, metrics collection and disk/terminal output are outside the reported pipeline stage costs. These measurements are not hard real-time or energy estimates.

A successful exit means the requested replay completed; it **does not certify accuracy or latency**. Inspect `totals.deadline_misses` and phase accuracies. The `noise_window` phase exists in clean controls too, covering the corresponding uncorrupted rows. Pre-bomb scores exclude warm-up. Post-window scores retain the permanent feature shift. Training uses observed labels; clean labels are retained only for evaluation. Fixed seeds reproduce injection positions, but timing-driven policy actions can vary with machine load.

Exit codes: 0 completed, 1 runtime failure, 2 invalid input/dependencies, 130 interrupted. This is a local validation harness, not a claim that the full application is production hardened.
