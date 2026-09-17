# Panel demonstration (3–5 minutes)

The demo shows one causal chain on one screen and one timeline:

**data change → drift → performance drop → detection → adaptation → recovery → cost → comparison.**

## Before the session

1. Start both servers:
   ```bash
   cd backend && PYTHONHASHSEED=0 .venv/bin/uvicorn adaptiveml.api.app:app --port 8000
   cd frontend && npm run dev
   ```
2. Open `http://localhost:5173`, check the **Connected** badge in the top bar.
3. Run the `compare_methods` experiment **once beforehand** (Experiments tab). The comparison section of
   the demo then opens instantly instead of waiting for trials.
4. Plug in the power adapter (battery runs are slower) and close other applications.
5. Pick the theme that reads best on the projector (Auto / Light / Dark in the top bar).

## Script

| Time | Who | Where | What to do and say |
|---|---|---|---|
| 0:00–0:40 | Review member | **Method** tab | The problem: models trained once lose accuracy when the data changes. Show the traceability table: each component names the paper reference it implements and the gap it addresses (G1–G6). |
| 0:40–1:10 | Utsav | **Live** tab | Press **🎬 Demo mode**. "This is the configuration we validated on 20 held-out seeds." Point at the pipeline strip: seven stages, each with its measured time per sample. |
| 1:10–1:50 | Utsav | Live | Warm-up ends, both methods predict the same samples. Point at Model / Stream / System health — accuracy *and* latency, CPU and memory together. |
| 1:50–2:30 | Utsav | Live | At sample 10,000 the caption says **the data changed**. Show the data snapshot: the points look the same, the boundary moved — that is concept drift, not a change of inputs. Both accuracy lines fall. |
| 2:30–3:10 | Utsav | Live | **Drift detected** — the event log gives the sample and the detector's error estimate. The state strip moves to **Adapting**: a replacement model trains while the old one keeps serving. Then it is promoted. |
| 3:10–3:40 | Utsav | Live | The **episode card** reads the whole story in numbers: accuracy before, lowest after the drift, after adaptation, the detection delay and how many samples the replacement needed. The static line stays low — that is the train-once pipeline. |
| 3:40–4:20 | Research member | **Experiments** → the `compare_methods` run | The table: accuracy and F1 next to latency, CPU per sample, memory and model size. ARF reaches a slightly higher accuracy at roughly twenty times the CPU cost per sample and a far larger model — the accuracy–cost trade-off the review asked for. |
| 4:20–5:00 | Research member | Same page | Press **Re-run and check reproducibility**: same config and seed, fresh processes, identical predictions. Close with: *"the prototype evaluates adaptation not only by predictive performance, but also by latency and resource efficiency."* |

## Optional extras (if there is time or a question)

- **Simulated edge profile:** start the `demo_edge` scenario. The banner states that budgets are enforced
  in software with placeholder values. Under the budget the pipeline first learns from fewer samples and
  then uses fewer features, and every decision is logged with the measurement that caused it.
- **Inject drift by hand:** the `free_play` scenario, then **⚡ Inject drift**. The drift is scheduled a
  few hundred samples ahead and written into the run's configuration, so the run still replays exactly.
- **The hard scenario:** `hard_scenario` is the configuration where detection failed in 9 of 10 seeds.
  Showing it is a strength — it is a measured limitation of ADWIN under noise, which our review cites [5].

## Questions to expect

| Question | Answer |
|---|---|
| "Is this a new algorithm?" | No. It integrates published techniques (ADWIN [5], Hoeffding trees, ARF [20], online feature selection [4], adaptive normalisation [19]) into one measured pipeline. |
| "Did you run this on an edge device?" | No. The edge profile is a software simulation on this laptop with placeholder budgets, and it is labelled as such everywhere. |
| "Are the numbers real?" | Every number comes from a stored run: configuration, seed, environment and per-sample outcomes are all in the exported bundle. |
| "Why did it adapt a second time?" | The detector reacted to a genuine rise in the model's own error, with no second drift in the data. It is reported as measured; the cause is under investigation. |
| "Why is the live latency higher than in the report?" | Paced runs process a sample after a sleep, so caches are cold. The figures of record come from isolated max-speed trials. |

## If something fails

- The run crashing is logged as an error state, and the partial run is still saved.
- If the live run misbehaves, open **Experiments** and present a stored run — the data and charts are the same.
- The API refuses to run an experiment while a live run is active; stop the live run first.
