"""Resource profiles: Standard, and a *simulated* edge-constrained profile.

Measurements are always taken on the local machine; a simulated profile only enforces budgets in
software, and no slower CPU is emulated. Budget values are a research-team decision
(docs/architecture.md §4.7). The edge values below are PLACEHOLDERS, chosen so that the constraint
binds for the adaptive Hoeffding-tree pipeline on the development laptop (≈19 µs/sample against a
15 µs budget) in order to exercise the mechanism. They are not derived from any device.
"""

from __future__ import annotations

from adaptiveml.config.schema import PipelineConfig, ProfileConfig, ResourceBudgets

STANDARD = ProfileConfig()
EDGE_SIM = ProfileConfig(
    name="edge_sim",
    label="Simulated edge-constrained",
    simulated=True,
    placeholder=True,
    budgets=ResourceBudgets(
        compute_share=0.03,
        nominal_rate=2_000,
        model_memory_mib=1.0,
        allow_background=False,
        max_update_stride=4,
        min_features=1,
    ),
)
BUILTIN_PROFILES = {p.name: p for p in (STANDARD, EDGE_SIM)}


def apply_profile(cfg: PipelineConfig, profile: ProfileConfig) -> PipelineConfig:
    """The static part of a profile: caps that hold for the whole trial."""
    b = profile.budgets
    fs, learner, adaptation = cfg.feature_selection, cfg.learner, cfg.adaptation
    if b.feature_budget_k is not None:
        cap = b.feature_budget_k if fs.k_max is None else min(fs.k_max, b.feature_budget_k)
        fs = fs.model_copy(update={"k_max": cap})
    if b.model_memory_mib is not None:
        learner = learner.model_copy(
            update={
                "max_size_mib": min(learner.max_size_mib, b.model_memory_mib),
                "memory_estimate_period": min(learner.memory_estimate_period, 1_000),
            }
        )
    if not b.allow_background:
        adaptation = adaptation.model_copy(update={"allow_background": False})
    return cfg.model_copy(update={"feature_selection": fs, "learner": learner, "adaptation": adaptation})


def per_sample_budget_ns(profile: ProfileConfig, rate: float | None) -> float | None:
    """The dynamic part: the service-time budget per sample, from a share of one core.

    At a paced rate R the pipeline may spend compute_share / R seconds per sample; at max speed the
    profile's nominal rate is used, so paced and max-speed trials face the same budget.
    """
    b = profile.budgets
    effective_rate = rate or b.nominal_rate
    if b.compute_share is None or effective_rate is None:
        return None
    return b.compute_share / effective_rate * 1e9
