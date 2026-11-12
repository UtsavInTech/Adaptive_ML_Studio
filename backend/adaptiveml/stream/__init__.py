from adaptiveml.config import StreamConfig
from adaptiveml.stream.sea import GroundTruthDrift, SeaScenario, label_flip_fraction
from adaptiveml.stream.static import StaticScenario, catalog
from adaptiveml.stream.streaming import StreamingScenario


def dataset_scenario(cfg: StreamConfig) -> StaticScenario | StreamingScenario:
    """The reader for a registered dataset: row-by-row from disk for large files, in memory otherwise."""
    entry = next((e for e in catalog() if e["id"] == cfg.dataset), None)
    if entry is not None and entry.get("streaming"):
        return StreamingScenario(cfg)
    return StaticScenario(cfg)


def make_scenario(cfg: StreamConfig, seed: int) -> SeaScenario | StaticScenario | StreamingScenario:
    if cfg.scenario == "csv":
        return dataset_scenario(cfg)
    if cfg.scenario == "sea":
        return SeaScenario(cfg, seed)
    raise ValueError(f"unknown scenario: {cfg.scenario}")


__all__ = ["GroundTruthDrift", "SeaScenario", "StreamingScenario", "dataset_scenario", "label_flip_fraction", "make_scenario"]
