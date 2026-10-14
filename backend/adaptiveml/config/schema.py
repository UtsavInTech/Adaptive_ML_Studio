"""Configuration schema shared by the engine, the CLI and the API.

Unknown keys are rejected, so a typo in an experiment file fails loudly instead of silently falling
back to a default. The resolved configuration of every run is written to its result bundle.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MethodName = Literal["static", "incremental", "adaptive", "arf"]
DriftKind = Literal["abrupt", "gradual", "incremental", "recurring"]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DriftSpec(_Frozen):
    """A concept change in a synthetic stream, placed by sample index (never by wall-clock time)."""

    position: int = Field(ge=1, description="0-based sample index at the centre of the change")
    width: int = Field(default=1, ge=1, description="1 = abrupt; >1 = gradual transition width")
    to_variant: int = Field(ge=0, le=3, description="SEA concept after the change")


class InjectedDrift(_Frozen):
    """A controlled change applied to a real dataset replay at a known row.

    No row is added, removed or reordered and no label is altered. From `start` onward the values of
    two input columns are exchanged, so the relationship a model learned between those columns and
    the label no longer holds. *How* the exchange arrives is the drift type:

      abrupt       every row from `start` is exchanged
      gradual      over `width` rows a rising share of rows is exchanged; old and new rows are mixed
      incremental  over `width` rows every row is a blend that moves steadily from old to new
      recurring    exchanged for `period` rows, original for `period` rows, and so on

    Because the position is known, scores before, during and after the change can be measured. This
    is an injected change on top of real data, and every result that uses it says so.
    """

    kind: DriftKind
    start: int = Field(ge=1, description="0-based index of the first row the change can affect")
    width: int = Field(default=1, ge=1, description="rows the change takes to complete (abrupt/recurring: 1)")
    period: int | None = Field(default=None, ge=1, description="recurring only: rows each arrangement lasts")
    swap: tuple[str, str] = Field(description="the two input columns whose values are exchanged")

    @model_validator(mode="after")
    def _coherent(self) -> InjectedDrift:
        if self.swap[0] == self.swap[1]:
            raise ValueError("the two exchanged columns must be different")
        if self.kind in ("abrupt", "recurring") and self.width != 1:
            raise ValueError(f"{self.kind} drift switches at once: width must be 1")
        if self.kind in ("gradual", "incremental") and self.width < 2:
            raise ValueError(f"{self.kind} drift needs a transition of at least 2 rows")
        if (self.kind == "recurring") != (self.period is not None):
            raise ValueError("period is required for recurring drift, and only valid for it")
        return self

    @property
    def end(self) -> int:
        """Index of the first row at which the first change is complete."""
        return self.start + self.width


class StreamConfig(_Frozen):
    scenario: Literal["sea", "csv"] = "sea"
    dataset: str | None = None
    dataset_sha256: str | None = None
    injection: InjectedDrift | None = None
    length: int = Field(default=12_000, gt=0)
    noise: float = Field(default=0.1, ge=0.0, le=0.5, description="probability of flipping a label")
    initial_variant: int = Field(default=0, ge=0, le=3)
    drifts: tuple[DriftSpec, ...] = ()
    rate: float | None = Field(default=None, gt=0, le=1_000_000, description="samples/s; None = max speed")

    @model_validator(mode="after")
    def _drifts_inside_stream(self) -> StreamConfig:
        if self.scenario == "csv":
            if not self.dataset:
                raise ValueError("CSV replay requires a registered dataset")
            if self.drifts or self.noise != 0 or self.initial_variant != 0:
                raise ValueError("CSV replay requires noise=0 and cannot inject synthetic concepts")
            if self.injection is not None and self.injection.end >= self.length:
                raise ValueError(
                    f"the injected change (rows {self.injection.start:,}–{self.injection.end:,}) "
                    f"must finish before the replay ends ({self.length:,} rows)"
                )
        elif self.dataset is not None or self.dataset_sha256 is not None or self.injection is not None:
            raise ValueError("dataset and injection fields are only valid for CSV replay")
        positions = [d.position for d in self.drifts]
        if any(b <= a for a, b in zip(positions, positions[1:])):
            raise ValueError("drift positions must be strictly increasing")
        if positions and positions[-1] >= self.length:
            raise ValueError(
                f"drift position ({positions[-1]:,}) is beyond stream length ({self.length:,})"
            )
        return self


class PreprocessingConfig(_Frozen):
    scaler: Literal["adaptive_standard", "standard", "none"] = "adaptive_standard"
    # Weight of the newest sample in the exponentially weighted mean/variance (effective memory
    # ≈ 2/α samples). River's default (0.3 ≈ 6 samples) re-standardises every sample against a
    # jittering mean, which moves a tree's learned split thresholds; see docs/performance.md.
    fading_factor: float = Field(default=0.001, gt=0.0, lt=1.0)
    clip: float | None = Field(default=5.0, gt=0.0, description="in standard deviations; needs a scaler")


class FeatureSelectionConfig(_Frozen):
    method: Literal["ofs_truncation", "none"] = "ofs_truncation"
    k: int | None = Field(default=None, ge=1, description="None = ceil(2n/3)")
    k_max: int | None = Field(default=None, ge=1, description="upper bound set by a resource profile")
    learning_rate: float = Field(default=0.05, gt=0.0)


class LearnerConfig(_Frozen):
    type: Literal["hoeffding_tree", "logistic_regression", "gaussian_nb", "arf"] = "hoeffding_tree"
    grace_period: int = Field(default=200, ge=1)
    max_size_mib: float = Field(default=100.0, gt=0.0)
    memory_estimate_period: int = Field(default=1_000_000, ge=1, description="how often River checks max_size")
    n_models: int = Field(default=10, ge=1, description="ARF only")


class DetectorConfig(_Frozen):
    type: Literal["adwin"] = "adwin"
    delta_drift: float = Field(default=0.002, gt=0.0, lt=1.0)
    delta_warning: float | None = Field(default=0.01, gt=0.0, lt=1.0)
    clock: int = Field(default=32, ge=1)


class AdaptationConfig(_Frozen):
    allow_background: bool = True  # resource profiles may disallow parallel replacement models
    background_min_samples: int = Field(default=200, ge=1, description="samples before a replacement is promoted")
    background_timeout: int = Field(default=2_000, ge=1, description="discard an unused warning-started replacement")
    cooldown: int = Field(default=300, ge=0)
    react_to_error_decrease: bool = False


class PipelineConfig(_Frozen):
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    feature_selection: FeatureSelectionConfig = Field(default_factory=FeatureSelectionConfig)
    learner: LearnerConfig = Field(default_factory=LearnerConfig)
    detector: DetectorConfig = Field(default_factory=DetectorConfig)
    adaptation: AdaptationConfig = Field(default_factory=AdaptationConfig)


class StabilityConfig(_Frozen):
    """Parameters of the *reference* stability computations. The formula is a team decision."""

    pre_window: int = Field(default=1_000, ge=1)
    horizon: int = Field(default=3_000, ge=1)
    window: int = Field(default=500, ge=1)
    tolerance: float = Field(default=0.02, ge=0.0)
    sustain: int = Field(default=500, ge=0)
    post_gap: int = Field(default=0, ge=0)


class PhaseConfig(_Frozen):
    """Row windows for the before / during / after scores around a change at a known position.

    before  the `before` rows immediately ahead of the change
    during  from the first changed row until `settle` rows after the change is complete
    after   the `after` rows that follow

    Like the stability figures these are reference computations: the window sizes are configurable
    and the choice of definition belongs to the research workstream.
    """

    before: int = Field(default=2_000, ge=1)
    settle: int = Field(default=1_000, ge=0)
    after: int = Field(default=2_000, ge=1)


class EvaluationConfig(_Frozen):
    warmup: int = Field(default=1_000, ge=1)
    block_size: int = Field(default=100, ge=1)
    model_size_every: int = Field(default=2_000, ge=1)
    positive_class: bool | int | str = True
    stability: StabilityConfig = Field(default_factory=StabilityConfig)
    phases: PhaseConfig = Field(default_factory=PhaseConfig)
    # A control trial has no change of its own; this pins its before/during/after windows to the
    # rows of the trial it is the control for: (first changed row, first fully changed row).
    phase_anchor: tuple[int, int] | None = None


class ResourceBudgets(_Frozen):
    """Software-enforced budgets of a (simulated) resource profile. All None/permissive = no constraint."""

    compute_share: float | None = Field(default=None, gt=0, le=1, description="max fraction of one core")
    nominal_rate: float | None = Field(default=None, gt=0, description="samples/s for the budget at max speed")
    model_memory_mib: float | None = Field(default=None, gt=0)
    feature_budget_k: int | None = Field(default=None, ge=1)
    allow_background: bool = True
    max_update_stride: int = Field(default=1, ge=1)
    min_features: int = Field(default=1, ge=1)
    down_blocks: int = Field(default=3, ge=1, description="blocks over budget before stepping down")
    up_blocks: int = Field(default=10, ge=1, description="blocks under the margin before stepping up")
    up_margin: float = Field(default=0.8, gt=0, lt=1)


class ProfileConfig(_Frozen):
    name: str = "standard"
    label: str = "Standard"
    simulated: bool = False
    placeholder: bool = False
    budgets: ResourceBudgets = Field(default_factory=ResourceBudgets)


class TrialConfig(_Frozen):
    seed: int = 42
    stream: StreamConfig = Field(default_factory=StreamConfig)
    methods: tuple[MethodName, ...] = ("static", "adaptive")
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    profile: ProfileConfig = Field(default_factory=ProfileConfig)

    @model_validator(mode="after")
    def _consistent(self) -> TrialConfig:
        if not self.methods:
            raise ValueError("at least one method is required")
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("methods must not repeat")
        if self.evaluation.warmup >= self.stream.length:
            raise ValueError("warm-up must be shorter than the stream")
        if self.stream.drifts and self.stream.drifts[0].position <= self.evaluation.warmup:
            raise ValueError("the first drift must come after the warm-up period")
        if self.stream.injection is not None and self.stream.injection.start <= self.evaluation.warmup:
            raise ValueError("the injected change must come after the warm-up period")
        anchor = self.evaluation.phase_anchor
        if anchor is not None and not (self.evaluation.warmup < anchor[0] < anchor[1] <= self.stream.length):
            raise ValueError("phase_anchor must lie after the warm-up and inside the stream")
        return self


CONTROL_SUFFIX = "__control"


class ExperimentConfig(_Frozen):
    """A set of trials — every method × profile × rate × seed — each run alone in a fresh process."""

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    base: TrialConfig = Field(default_factory=TrialConfig)
    profiles: tuple[ProfileConfig, ...] = Field(default_factory=lambda: (ProfileConfig(),))
    rates: tuple[float | None, ...] = (None,)
    seeds: tuple[int, ...] = (42,)
    # With an injected change on real data: also run every method on the untouched rows, scored over
    # the same row windows, so a drop can be attributed to the change rather than to the data itself.
    control: bool = False

    @field_validator("rates")
    @classmethod
    def _positive_rates(cls, rates):
        if not rates or any(r is not None and r <= 0 for r in rates):
            raise ValueError("rates must be positive samples/s, or null for max speed")
        return rates

    @field_validator("seeds", "profiles")
    @classmethod
    def _non_empty(cls, values):
        if not values:
            raise ValueError("at least one value is required")
        return values

    def trials(self) -> list[tuple[str, TrialConfig]]:
        out = []
        for seed in self.seeds:
            for profile in self.profiles:
                for rate in self.rates:
                    stream = self.base.stream.model_copy(update={"rate": rate})
                    for method in self.base.methods:
                        cfg = self.base.model_copy(
                            update={"seed": seed, "methods": (method,), "profile": profile, "stream": stream}
                        )
                        rate_label = "max" if rate is None else f"{rate:g}ps"
                        trial_id = f"{method}__{profile.name}__{rate_label}__s{seed}"
                        out.append((trial_id, cfg))
                        injection = stream.injection
                        if self.control and injection is not None:
                            untouched = cfg.model_copy(update={
                                "stream": stream.model_copy(update={"injection": None}),
                                "evaluation": cfg.evaluation.model_copy(
                                    update={"phase_anchor": (injection.start, injection.end)}
                                ),
                            })
                            out.append((f"{trial_id}{CONTROL_SUFFIX}", untouched))
        return out
