"""Incremental learners and the slot that holds a model with its applied feature set."""

from __future__ import annotations

from dataclasses import dataclass

from river import base, ensemble, forest, linear_model, naive_bayes, tree

from adaptiveml.config import LearnerConfig


class NoChangeClassifier(base.Classifier):
    """Predicts the label of the previous row ("repeat the last label").

    The reference for streams whose labels come in runs. It uses no features at all, so any method
    that does not beat it has learned nothing about the inputs. Its accuracy is the p_nc term of
    the kappa-temporal statistic (Žliobaitė et al., 2015; Bifet et al., 2015).
    """

    def __init__(self):
        self.last = None

    def learn_one(self, x, y):
        self.last = y

    def predict_proba_one(self, x):
        return {} if self.last is None else {self.last: 1.0}

    def predict_one(self, x, **kwargs):
        return self.last  # None before the first label; the pipeline then uses its fallback label


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
    if cfg.type == "no_change":
        return NoChangeClassifier()
    if cfg.type == "srp":
        # Streaming Random Patches (Gomes et al., 2019): Hoeffding trees on random feature subsets
        # and bootstrap weights, each with its own drift detector (River's defaults).
        return ensemble.SRPClassifier(
            model=tree.HoeffdingTreeClassifier(grace_period=cfg.grace_period, **memory),
            n_models=cfg.n_models, seed=seed,
        )
    if cfg.type == "lev_bag":
        # Leveraging bagging (Bifet et al., 2010): Poisson(6) bagging with ADWIN per member.
        return ensemble.LeveragingBaggingClassifier(
            model=tree.HoeffdingTreeClassifier(grace_period=cfg.grace_period, **memory),
            n_models=cfg.n_models, seed=seed,
        )
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
