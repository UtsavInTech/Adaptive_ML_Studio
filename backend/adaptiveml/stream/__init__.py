from adaptiveml.config import StreamConfig
from adaptiveml.stream.sea import GroundTruthDrift, SeaScenario, label_flip_fraction


def make_scenario(cfg: StreamConfig, seed: int) -> SeaScenario:
    if cfg.scenario == "sea":
        return SeaScenario(cfg, seed)
    raise ValueError(f"unknown scenario: {cfg.scenario}")


__all__ = ["GroundTruthDrift", "SeaScenario", "label_flip_fraction", "make_scenario"]
