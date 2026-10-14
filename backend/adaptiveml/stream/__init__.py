from adaptiveml.config import StreamConfig
from adaptiveml.stream.sea import GroundTruthDrift, SeaScenario, label_flip_fraction
from adaptiveml.stream.static import StaticScenario


def make_scenario(cfg: StreamConfig, seed: int) -> SeaScenario | StaticScenario:
    if cfg.scenario == "csv":
        return StaticScenario(cfg)
    if cfg.scenario == "sea":
        return SeaScenario(cfg, seed)
    raise ValueError(f"unknown scenario: {cfg.scenario}")


__all__ = ["GroundTruthDrift", "SeaScenario", "label_flip_fraction", "make_scenario"]
