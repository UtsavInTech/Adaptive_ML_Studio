"""Adaptation policy: a transparent rule ladder from detector signals to the adaptation options
named in §VI of the review (update parameters · choose the right model · retrain if necessary).

    warning                          → start training a replacement model in the background
    drift, replacement ready         → swap it in now
    drift, replacement not ready     → keep training it; promote it once it has enough samples
    drift, background not allowed    → reset to a fresh model now (cheaper, colder start)

The background-replacement strategy follows ARF [20]: the replacement learns only from samples
after the warning/detection, so it is not trained on the outdated concept. It is rule-based and not
optimised; it is not presented as a novel method.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from adaptiveml.config import AdaptationConfig
from adaptiveml.drift import Signal


class Action(StrEnum):
    NONE = "none"
    IGNORE = "ignore"
    START_BACKGROUND = "start_background"
    SWAP = "swap"
    PREPARE = "prepare"
    RESET = "reset"


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str = ""


_NOTHING = Decision(Action.NONE)


class AdaptationPolicy:
    def __init__(self, cfg: AdaptationConfig):
        self._cfg = cfg

    def decide(
        self,
        signal: Signal,
        *,
        error_increased: bool,
        sample_index: int,
        last_adaptation: int | None,
        background_trained: int | None,
        adaptation_pending: bool = False,
    ) -> Decision:
        cfg = self._cfg
        if signal is Signal.NONE:
            return _NOTHING
        rising = error_increased or cfg.react_to_error_decrease
        in_cooldown = last_adaptation is not None and sample_index - last_adaptation < cfg.cooldown

        if signal is Signal.WARNING:
            if in_cooldown or adaptation_pending or not cfg.allow_background or background_trained is not None or not rising:
                return _NOTHING
            return Decision(Action.START_BACKGROUND, "warning detector fired (error rate rose)")

        if not rising:
            return Decision(Action.IGNORE, "change detected, but the error rate decreased")
        if adaptation_pending:
            return Decision(Action.IGNORE, "a replacement model is already being prepared")
        if in_cooldown:
            return Decision(Action.IGNORE, f"within the {cfg.cooldown}-sample cooldown after the last adaptation")
        if not cfg.allow_background:
            return Decision(Action.RESET, "drift detected; background models are not allowed, so a fresh model replaces the current one")
        needed = cfg.background_min_samples
        if background_trained is not None and background_trained >= needed:
            return Decision(Action.SWAP, f"drift detected; replacement model trained on {background_trained} samples")
        return Decision(
            Action.PREPARE,
            f"drift detected; replacement model has {background_trained or 0} of {needed} samples — promoting it when ready",
        )
