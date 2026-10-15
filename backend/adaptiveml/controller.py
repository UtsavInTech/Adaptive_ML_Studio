"""Shared per-instance policy for CLI and web workers.

Paper subset: R1 increasing-error drift refresh, R3 latency feature reduction,
R4 low-accuracy refresh. Cooldown is operational bookkeeping, not paper R5.
CPU/energy gating and memory recovery (paper R2/R5) remain outside this subset.
"""
from collections import Counter, deque
from time import perf_counter_ns

class Controller:
    def __init__(self, max_ms=15.0, floor=0.7, cooldown=500):
        self.max_ms, self.floor, self.cooldown = max_ms, floor, cooldown
        self.last_refresh = -cooldown
        self.actions = Counter()

    def step(self, index, service_ms, accuracy, engine, events):
        actions = []
        if any(e['type'] == 'drift_detected' and e.get('error_increased') for e in events):
            actions.append('R1_DRIFT')
            if not any(e['type'] == 'adaptation_completed' for e in events):
                engine.refresh(index, len(engine.features), 'R1: increasing-error drift')
            self.last_refresh = index
        if any(e['type'] == 'adaptation_completed' for e in events):
            self.last_refresh = index
        if service_ms > self.max_ms:
            old = len(engine.features)
            if old > 1:
                engine.refresh(index, max(1, old // 2), 'R3: per-row latency deadline exceeded')
                self.last_refresh = index
                actions.append(f'R3_HALVE_{old}_TO_{len(engine.features)}')
            else:
                actions.append('R3_AT_MINIMUM_UNRESOLVED')
        elif accuracy is not None and accuracy < self.floor:
            if index - self.last_refresh >= self.cooldown:
                engine.refresh(index, len(engine.features), 'R4: rolling accuracy below floor')
                self.last_refresh = index
                actions.append('R4_LOW_ACCURACY_REFRESH')
            else:
                actions.append('COOLDOWN')
        self.actions.update(actions)
        return actions


class PipelineController:
    """Adapt a MethodPipeline to the same Controller used by the CLI.

Controller time is included in the adaptation stage and service total. Each
instance is checked; dashboard blocks only aggregate the resulting measurements.
"""
    def __init__(self, pipe, max_ms=15.0, floor=.7, cooldown=500, window=500):
        self.pipe = pipe
        self.policy = Controller(max_ms, floor, cooldown)
        self.window = deque(maxlen=window)
        self.budget_ns = max_ms * 1e6
        self.constrained = False

    @property
    def decisions(self):
        return sum(v for k, v in self.policy.actions.items() if k != 'COOLDOWN')

    @property
    def features(self):
        return self.pipe.active.features

    def refresh(self, index, k, reason):
        self.pipe.reconfigure_features(index, k, reason, immediate=True)

    def process(self, index, x, y):
        offset = len(self.pipe.events)
        prediction, service, stages = self.pipe.process(index, x, y)
        start = perf_counter_ns()
        if index >= self.pipe._warmup:
            self.window.append(int(prediction == y))
        accuracy = sum(self.window)/len(self.window) if len(self.window) == self.window.maxlen else None
        self.constrained = service > self.budget_ns
        actions = self.policy.step(index, service/1e6, accuracy, self, self.pipe.events[offset:])
        for action in actions:
            if action != 'COOLDOWN':
                self.pipe.emit(index, 'controller_action', action=action, service_ms=service/1e6, accuracy=accuracy)
        elapsed = perf_counter_ns() - start
        measured = list(stages)
        measured[4] += elapsed
        return prediction, service + elapsed, tuple(measured)
