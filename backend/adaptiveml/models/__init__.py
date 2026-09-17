"""Incremental learners and the slot that holds a model with its applied feature set."""

from __future__ import annotations

from dataclasses import dataclass

from river import base, forest, linear_model, naive_bayes, tree

from adaptiveml.config import LearnerConfig


def make_learner(cfg: LearnerConfig, seed: int) -> base.Classifier:
    memory = {"max_size": cfg.max_size_mib, "memory_estimate_period": cfg.memory_estimate_period}
    if cfg.type == "hoeffding_tree":
        return tree.HoeffdingTreeClassifier(grace_period=cfg.grace_period, **memory)
    if cfg.type == "logistic_regression":
        return linear_model.LogisticRegression()
    if cfg.type == "gaussian_nb":
        return naive_bayes.GaussianNB()
    if cfg.type == "arf":
        return forest.ARFClassifier(n_models=cfg.n_models, seed=seed, **memory)
    raise ValueError(f"unknown learner: {cfg.type}")


@dataclass(slots=True)
class ModelSlot:
    model: base.Classifier
    features: tuple[str, ...]
    version: int
    started_at: int
    trained_on: int = 0


def project(x: dict, features: tuple[str, ...]) -> dict:
    return {f: x[f] for f in features}
