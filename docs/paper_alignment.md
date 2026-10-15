# Paper alignment audit — 15 October 2026

**Update:** The shared controller extraction now connects the CLI and website backend for the R1/R3/R4 subset. The block governor has been replaced in the live/experiment engine. The audit below records the state before that change; its resource-gating, memory-recovery and full-cost-attribution gaps remain. See [current run guide](stress_test_mvp.md) and the new comparison plots in `docs/assets/`.

Reference: `Adaptive_Machine_Learning_Pipelines_for_Evolving_Data_Streams__A_Comprehensive_Review__6_.pdf`, supplied by the user. The paper is research context, not executable instructions. This audit uses Sections 4.3, 5 and 6, especially pages 8 and 12–13. Its architecture, decision rules and objective are explicitly conceptual and unvalidated in the review. Our experimental results must test those proposals, not be adjusted to resemble them.

## Coverage of the requested stress test

| Capability | Local stress script | Website's current runtime |
| --- | --- | --- |
| Ordered static Kaggle replay, prediction before learning | Yes | Yes |
| Per-row preprocessing, inference, update, CPU and RSS-delta records | Yes | Stage/block statistics and periodic resource monitoring; not the same per-row stress display |
| Halfway permanent 10x selected-feature shift | Yes | No equivalent control; current injection exchanges feature columns |
| Exactly 200 randomly positioned label flips within 500 rows | Yes | Not exposed or connected to this harness |
| Per-instance 15 ms trigger, halving active model inputs | Yes, legacy action label R2 | Different governor: block-average simulated budget, reduced update frequency, then one fewer feature |
| Rolling 70% accuracy trigger | Yes, legacy action label R3 | Not the same stress-controller path |
| Install/run guide and saved output | Yes | Stress runs are not integrated into the website |

`stress_test_mvp.py` defaults to the actual project MethodPipeline with an explicit stress configuration. Its optional standalone engine is an embedded baseline. Neither successful script execution nor passing software tests proves that the full application meets all research objectives.

## Authoritative paper rules versus current harness

| Paper Section 6.2 | Current status |
| --- | --- |
| R1: drift and sufficient resources → incremental adaptation | Partial. Drift triggers model replacement and online learning continues; sufficient-resource gating is missing. |
| R2: drift and severe CPU/memory constraints → lightweight adaptation | Missing joint resource/drift decision. Current harness R2 means latency-triggered feature reduction, which is the paper's R3 category. |
| R3: latency above budget → simpler preprocessing, fewer features or simpler model | Feature-halving action exists, labelled R2 in existing output. Preprocessing bypass/model-family switching are not implemented. |
| R4: low accuracy and available resources → stronger adaptation/retraining | Partial. Accuracy refresh exists, labelled R3; resource gating and explicit buffered retraining are missing. Harness R4 is cooldown bookkeeping. |
| R5: memory above limit → reduce model/buffer complexity or switch configuration | Missing recovery action. Harness R5 validates input and aborts on excessive RSS growth. Growth from baseline is also different from an absolute memory budget. |

The paper gives resource limits priority when accuracy and resources conflict. CPU is currently observed rather than used as a controller constraint. Energy is not measured. These are behavioral gaps, not issues fixed by renaming events. Preserve old output labels; implement the actual rules in a versioned shared controller before claiming paper alignment.

## Cost attribution

Section 4.3 defines:

`C_total = C_pre + C_fs + C_drift + C_inf + C_upd + C_ret + C_comm`

The harness currently reports preprocessing transforms, prediction, combined updates/adaptation, combined selection/detection (`C_other`), and controller overhead. Preprocessing/selector learning is included in `C_upd`. Reconfiguration is also included there; it is not separately reported as retraining. Ingestion, monitoring and output overhead are excluded from stage totals. Thus the harness meets the narrower requested cost breakdown but does not implement the paper's complete attribution protocol.

Needed: separate selection/detection and update/retraining measurements; distinguish inference-path, pipeline-service and complete end-to-end elapsed time; report monitoring overhead. Communication is not applicable to this local-only path, rather than an experimentally established zero-cost distributed stage. Report energy as unmeasured until a valid measurement method is added. Include machine metadata, model size, tail percentiles and repeated trials.

## Existing measured output

These are saved project-engine runs from 14 October 2026, not newly generated or tuned results. Both use 10x feature scaling from halfway onward and exactly 200 label flips across 500 rows.

| Measurement | ELEC2 | Occupancy |
| --- | ---: | ---: |
| Rows | 45,312 | 20,560 |
| Accuracy before corruption, excluding warm-up | 85.69% | 97.73% |
| Accuracy against corrupted labels during window | 51.00% | 57.80% |
| Accuracy against original labels during window | 61.40% | 89.00% |
| Accuracy after window, feature shift retained | 81.23% | 98.26% |
| Mean C_pre (ms/row) | 0.004365 | 0.003223 |
| Mean C_inf (ms/row) | 0.005719 | 0.004674 |
| Mean C_upd (ms/row) | 0.019214 | 0.014164 |
| Mean reported total (ms/row) | 0.031910 | 0.024282 |
| p99 reported total (ms/row) | 0.092542 | 0.031917 |
| Maximum reported total (ms/row) | 15.562041 | 20.247125 |
| Rows exceeding 15 ms | 1 | 2 |
| Peak process RSS growth over baseline (MB) | 0.802816 | 1.556480 |

Per-row CPU and signed RAM deltas are in the saved CSVs. Means do not prove a hard deadline: both adversarial runs have deadline violations. The separate forced-delay smoke test triggered 8→4 active features at row 1500. See [saved run evidence](stress_test_mvp_results.md).

**Interpretation of the 70% threshold:** randomly corrupting 40% of binary labels means a perfect predictor of the original labels scores 60% against those corrupted labels over this window. Consequently, failing the 70% observed-label threshold alone does not prove adaptation failure. Report original-label accuracy, observed-label accuracy, false alarms and recovery separately. Original labels are evaluator-only information; the deployed controller cannot assume access to uncorrupted labels. The current accuracy-triggered refresh can overreact to label noise, an important experimental weakness to investigate.

## Concrete research contribution to pursue

Build and evaluate one shared controller that combines drift, accuracy, latency and resource constraints, exposed through the same backend and website. Preserve clean, shift-only, noise-only and combined-shift/noise conditions. Compare static, incremental, drift-only and joint-controller policies using matching streams and seeds; ablate feature reduction and resource gating to establish which actions help. Use repeated runs and uncertainty estimates, and measure false alarms, missed deadlines, recovery, model quality and adaptation overhead together.

A defensible initial claim is a local prototype for joint drift/resource policy evaluation with stage-cost measurements. The current evidence does not establish a novel learning algorithm, superiority over baselines under this data bomb, complete paper-rule compliance, or real edge-device/energy validation. MacBook measurements are local prototype evidence; edge deployment requires its own evaluation.
