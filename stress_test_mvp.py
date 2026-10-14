#!/usr/bin/env python3
"""Local per-row adversarial validation; never changes source datasets.

Default --engine project exercises AdaptiveML's actual MethodPipeline with an
explicit stress profile (all features initially, immediate replacement, cooldown).
--engine standalone needs only psutil + river and embeds a small online baseline;
it validates the harness, not the application's production pipeline.

Proposed rules (the supplied request does not define the paper's R1–R5 mapping):
R1: increasing-error ADWIN drift -> model replacement/update (engine policy).
R2: per-row service latency > budget -> halve active features, retaining >=1.
R3: full rolling accuracy window below floor -> request model refresh.
R4: cooldown rate-limits R3 refreshes; it never hides R2 deadline violations.
R5: reject non-finite inputs/predictions and stop on errors or RAM-growth limit.

C_pre = preprocessing transform; C_inf = prediction; C_upd = adaptation + learning
(including preprocessing/feature-selector learning). C_other = selection + detection.
C_upd also includes controller-triggered replacements; C_policy is remaining rule
overhead: C_total = C_pre + C_inf + C_upd + C_other + C_policy.
CPU is process CPU time / elapsed monitored wall time (one core = 100%); very short
rows may report 0% due to OS counter resolution. RAM delta is signed RSS change,
not allocated object bytes; flat/negative values are legitimate. Disk/logging and
CSV ingestion are outside stage latency. Millisecond timestamps are observations,
not guarantees of hard real-time scheduling on macOS.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
import time
import uuid
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class DataBomb:
    """Permanent feature scaling + exactly 40% randomly placed flips in 500 rows."""
    def __init__(self, start, features, factor=10.0, window=500, fraction=0.4, seed=42, enabled=True):
        self.start, self.features, self.factor, self.window = start, tuple(features), factor, window
        self.enabled = enabled
        self.flips = set(random.Random(seed).sample(range(window), round(window * fraction)))

    def apply(self, index, x, y):
        changed = self.enabled and index >= self.start
        noisy = changed and index - self.start in self.flips
        out = dict(x)
        if changed:
            for feature in self.features:
                out[feature] *= self.factor
        return out, not y if noisy else y, changed, noisy


def rows(path, features, target, labels):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        required = set(features) | {target}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f'CSV is missing columns: {required - set(reader.fieldnames or [])}')
        for index, row in enumerate(reader):
            try:
                x = {key: float(row[key]) for key in features}
                if not all(math.isfinite(v) for v in x.values()):
                    raise ValueError('non-finite input')
                y = bool(labels[row[target].strip()])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f'Invalid CSV row {index + 2}: {exc}') from exc
            yield index, x, y


class StandaloneEngine:
    """Embedded online River baseline for running this file outside the repository."""
    def __init__(self, features, warmup, cooldown, seed):
        from river import drift, preprocessing, tree
        self._tree, self._drift = tree, drift
        self.features = tuple(features)
        self.pre = preprocessing.StandardScaler()
        self.model = tree.HoeffdingTreeClassifier()
        self.detector = drift.ADWIN()
        self.warmup, self.cooldown, self.last_reset = warmup, cooldown, -cooldown
        self.events = []
        self.fault_ms = 0.0
        self.refresh_ns = 0

    def refresh(self, index, k, reason):
        started = time.perf_counter_ns()
        self.features = self.features[:k]
        self.model = self._tree.HoeffdingTreeClassifier()
        self.detector = self._drift.ADWIN()
        self.last_reset = index
        self.events.append({'i': index, 'type': 'adaptation_completed', 'reason': reason})
        self.refresh_ns += time.perf_counter_ns() - started

    def process(self, index, x, y):
        t0 = time.perf_counter_ns()
        scaled = self.pre.transform_one(x)
        if self.fault_ms:
            time.sleep(self.fault_ms / 1000)
        t1 = time.perf_counter_ns()
        selected = {f: scaled[f] for f in self.features}
        t2 = time.perf_counter_ns()
        prediction = self.model.predict_one(selected)
        prediction = False if prediction is None else prediction
        t3 = time.perf_counter_ns()
        before = self.detector.estimation
        if index >= self.warmup:
            self.detector.update(int(prediction != y))
        detected = index >= self.warmup and self.detector.drift_detected
        increased = detected and self.detector.estimation > before
        t4 = time.perf_counter_ns()
        if detected:
            self.events.append({'i': index, 'type': 'drift_detected', 'error_increased': increased})
        if increased and index - self.last_reset >= self.cooldown:
            self.refresh(index, len(self.features), 'R1: increasing-error drift')
        t5 = time.perf_counter_ns()
        self.model.learn_one(selected, y)
        self.pre.learn_one(x)
        t6 = time.perf_counter_ns()
        return prediction, t6 - t0, (t1-t0, t2-t1, t3-t2, t4-t3, t5-t4, t6-t5)


class ProjectEngine:
    def __init__(self, features, warmup, cooldown, seed):
        sys.path.insert(0, str(ROOT / 'backend'))
        from adaptiveml.config import PipelineConfig
        from adaptiveml.pipeline import MethodPipeline, method_spec
        config = PipelineConfig.model_validate({
            'feature_selection': {'k': len(features)},
            'adaptation': {'allow_background': False, 'cooldown': cooldown},
        })
        self.pipe = MethodPipeline(method_spec('adaptive', config), features, warmup=warmup, seed=seed)
        self.profile = config.model_dump(mode='json')
        self.fault_ms = 0.0
        self.refresh_ns = 0
        original = self.pipe.pre.transform

        def transform(x):
            result = original(x)
            if self.fault_ms:
                time.sleep(self.fault_ms / 1000)
            return result
        self.pipe.pre.transform = transform

    @property
    def features(self):
        return self.pipe.active.features

    @property
    def events(self):
        return self.pipe.events

    def refresh(self, index, k, reason):
        started = time.perf_counter_ns()
        self.pipe.reconfigure_features(index, k, reason)
        if len(self.pipe.active.features) != k:
            raise RuntimeError('Requested feature reduction was not applied')
        self.refresh_ns += time.perf_counter_ns() - started

    def process(self, index, x, y):
        return self.pipe.process(index, x, y)


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
                engine.refresh(index, max(1, old // 2), 'R2: per-row latency deadline exceeded')
                self.last_refresh = index
                actions.append(f'R2_HALVE_{old}_TO_{len(engine.features)}')
            else:
                actions.append('R2_AT_MINIMUM_UNRESOLVED')
        elif accuracy is not None and accuracy < self.floor:
            if index - self.last_refresh >= self.cooldown:
                engine.refresh(index, len(engine.features), 'R3: rolling accuracy below floor')
                self.last_refresh = index
                actions.append('R3_LOW_ACCURACY_REFRESH')
            else:
                actions.append('R4_COOLDOWN')
        self.actions.update(actions)
        return actions


def cpu_seconds(process):
    times = process.cpu_times()
    return times.user + times.system


def source(args):
    if args.csv:
        if not args.features or not args.target or args.positive == args.negative:
            raise ValueError('Custom CSV requires --features, --target and two distinct label values')
        path = args.csv.resolve()
        features = tuple(v.strip() for v in args.features.split(','))
        labels = {args.negative: 0, args.positive: 1}
        target = args.target
        metadata = {'source': str(path), 'dataset': 'custom'}
    else:
        catalog = json.loads((ROOT / 'data/catalog.json').read_text())
        entry = next((e for e in catalog if e['id'] == args.dataset), None)
        if entry is None:
            raise ValueError(f'Unknown dataset: {args.dataset}')
        path = (ROOT / 'data' / entry['file']).resolve()
        features, target, labels = tuple(entry['features']), entry['target'], entry['labels']
        metadata = dict(entry)
    if len(features) < 2 or len(set(features)) != len(features) or target in features:
        raise ValueError('Choose at least two unique features and exclude the target')
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    if metadata.get('sha256', digest) != digest:
        raise ValueError('Source checksum differs from catalog')
    # Validation/counting pass uses constant memory; learning below still consumes one row at a time.
    available = sum(1 for _ in rows(path, features, target, labels))
    n = available if args.limit is None else args.limit
    if n > available or n < 2 * args.noise_window:
        raise ValueError('Replay must fit the file and leave the full noise window after its midpoint')
    warmup = args.warmup if args.warmup is not None else metadata.get('recommended_warmup', 1000)
    if not 1 <= warmup < n // 2:
        raise ValueError('Warm-up must end before the halfway data bomb; increase --limit or reduce --warmup')
    defaults = {'elec2': ('nswprice', 'nswdemand'), 'occupancy': ('Light', 'CO2')}
    critical = tuple(v.strip() for v in args.shift_features.split(',')) if args.shift_features else defaults.get(args.dataset, features[:max(1, len(features)//2)])
    if args.csv and not args.shift_features:
        critical = features[:max(1, len(features)//2)]
    if not critical or not set(critical).issubset(features):
        raise ValueError('Shift features must be input columns')
    return path, features, target, labels, n, warmup, critical, dict(metadata, sha256=digest)


def run(args):
    import psutil
    path, features, target, labels, n, warmup, critical, metadata = source(args)
    engine = (ProjectEngine if args.engine == 'project' else StandaloneEngine)(features, warmup, args.cooldown, args.seed)
    controller = Controller(args.max_latency_ms, args.accuracy_floor, args.cooldown)
    bomb = DataBomb(n//2, critical, args.scale, args.noise_window, args.noise_fraction, args.seed, not args.clean)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = args.output / stamp
    output.mkdir(parents=True, exist_ok=False)
    proc = psutil.Process()
    baseline = proc.memory_info().rss
    clock = time.perf_counter_ns
    started = clock()
    window = deque(maxlen=args.accuracy_window)
    phase_scores = {phase: Counter() for phase in ('before', 'noise_window', 'after')}
    totals = Counter()
    fields = ['index', 'elapsed_ms', 'phase', 'shifted', 'label_flipped', 'y_clean', 'y_observed', 'prediction',
              'C_pre_ms', 'C_inf_ms', 'C_upd_ms', 'C_other_ms', 'C_policy_ms', 'C_total_ms', 'fault_ms',
              'cpu_percent', 'ram_delta_mb', 'ram_growth_mb', 'active_features', 'rolling_accuracy', 'actions']
    summary = {'status': 'running', 'engine': args.engine, 'source': metadata,
               'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
               'warmup': warmup, 'rows_requested': n, 'bomb_index': n//2,
               'shift_features': critical, 'profile': getattr(engine, 'profile', 'embedded River baseline')}
    print(f'Output: {output}\nEngine: {args.engine}; rows={n}; warmup={warmup}; bomb index={n//2}; source sha256={metadata["sha256"]}')
    print('index elapsed_ms C_pre_ms C_inf_ms C_upd_ms C_total_ms CPU% RAM_delta_MB features accuracy action')
    status, error, processed = 'completed', None, 0
    lat_max = 0.0
    event_offset = 0
    stream = rows(path, features, target, labels)
    with (output/'iterations.csv').open('w', newline='') as metrics_file, (output/'events.jsonl').open('w') as event_file:
        writer = csv.DictWriter(metrics_file, fieldnames=fields)
        writer.writeheader()
        def event(payload):
            event_file.write(json.dumps(dict(payload, elapsed_ms=(clock()-started)/1e6), allow_nan=False)+'\n')
        try:
            for _ in range(n):
                index, original_x, clean_y = next(stream)
                x, y, shifted, flipped = bomb.apply(index, original_x, clean_y)
                if not all(math.isfinite(v) for v in x.values()):
                    raise ValueError('R5: non-finite input after data bomb')
                phase = 'before' if index < bomb.start else 'noise_window' if index < bomb.start+bomb.window else 'after'
                if index == bomb.start and not args.clean:
                    event({'index': index, 'type': 'DATA_BOMB', 'scale': args.scale, 'features': critical,
                           'noise_window': bomb.window, 'label_flips_planned': len(bomb.flips)})
                engine.fault_ms = args.fault_latency_ms if bomb.start <= index < bomb.start+args.fault_rows else 0.0
                rss0, cpu0 = proc.memory_info().rss, cpu_seconds(proc)
                wall0 = clock()
                prediction, service_ns, stages = engine.process(index, x, y)
                if prediction not in (True, False, 0, 1):
                    raise ValueError('R5: invalid binary prediction')
                if service_ns < 0 or any(t < 0 for t in stages) or sum(stages) != service_ns:
                    raise ValueError('R5: invalid stage accounting')
                new_events = engine.events[event_offset:]
                if index >= warmup:
                    window.append(int(prediction == y))
                    scores = phase_scores[phase]
                    scores.update(n=1, observed_correct=int(prediction == y), clean_correct=int(prediction == clean_y))
                accuracy = sum(window)/len(window) if len(window) == window.maxlen else None
                refresh_before = engine.refresh_ns
                policy0 = clock()
                actions = controller.step(index, service_ns/1e6, accuracy, engine, new_events)
                policy_ns = clock()-policy0
                policy_update_ns = engine.refresh_ns - refresh_before
                cpu1, rss1 = cpu_seconds(proc), proc.memory_info().rss
                wall_ns = clock()-wall0
                total_ms = (service_ns+policy_ns)/1e6
                record = dict(index=index, elapsed_ms=(clock()-started)/1e6, phase=phase,
                              shifted=shifted, label_flipped=flipped, y_clean=int(clean_y), y_observed=int(y), prediction=int(prediction),
                              C_pre_ms=stages[0]/1e6, C_inf_ms=stages[2]/1e6,
                              C_upd_ms=(stages[4]+stages[5]+policy_update_ns)/1e6, C_other_ms=(stages[1]+stages[3])/1e6,
                              C_policy_ms=(policy_ns-policy_update_ns)/1e6, C_total_ms=total_ms, fault_ms=engine.fault_ms,
                              cpu_percent=max(0, (cpu1-cpu0)/(wall_ns/1e9)*100), ram_delta_mb=(rss1-rss0)/1e6,
                              ram_growth_mb=(rss1-baseline)/1e6, active_features=len(engine.features),
                              rolling_accuracy=accuracy, actions=';'.join(actions))
                writer.writerow(record)
                for emitted in engine.events[event_offset:]:
                    event(emitted)
                event_offset = len(engine.events)
                for action in actions:
                    if action != 'R4_COOLDOWN':
                        event({'index': index, 'type': action, 'service_ms': service_ns/1e6, 'accuracy': accuracy})
                # Keep the engine's event storage bounded after writing to disk.
                engine.events.clear(); event_offset = 0
                processed += 1
                totals.update(flipped=int(flipped), shifted=int(shifted), deadline_misses=int(total_ms > args.max_latency_ms))
                for key in ('C_pre_ms', 'C_inf_ms', 'C_upd_ms', 'C_other_ms', 'C_policy_ms', 'C_total_ms'):
                    totals[key] += record[key]
                lat_max = max(lat_max, total_ms)
                if index % args.log_every == 0 or (actions and actions != ['R4_COOLDOWN']) or index == n-1:
                    acc = '-' if accuracy is None else f'{accuracy:.1%}'
                    print(f'{index:6} {record["elapsed_ms"]:10.3f} {record["C_pre_ms"]:9.4f} {record["C_inf_ms"]:9.4f} '
                          f'{record["C_upd_ms"]:9.4f} {total_ms:10.4f} {record["cpu_percent"]:6.1f} '
                          f'{record["ram_delta_mb"]:+10.4f} {len(engine.features):3} {acc:>6} {record["actions"]}', flush=True)
                if record['ram_growth_mb'] > args.max_ram_growth_mb:
                    raise MemoryError('R5: process RAM growth exceeded safety limit')
        except KeyboardInterrupt:
            status, error = 'interrupted', 'Stopped by user; partial results retained'
        except Exception as exc:
            status, error = 'failed', f'{type(exc).__name__}: {exc}'
            event({'type': 'R5_ABORT', 'index': processed, 'error': error})
        finally:
            stream.close()
    summary.update(status=status, error=error, rows_processed=processed, totals=dict(totals),
                   means_ms={k: totals[k]/processed if processed else None for k in fields if k.startswith('C_')},
                   max_total_ms=lat_max, policy_counts=dict(controller.actions),
                   phase_scores={phase: dict(c, observed_accuracy=c['observed_correct']/c['n'] if c['n'] else None,
                                             clean_accuracy=c['clean_correct']/c['n'] if c['n'] else None)
                                 for phase, c in phase_scores.items()},
                   note='Completion is not an accuracy/latency pass. Read deadline misses and phase scores. CPU/RSS have OS resolution limits.')
    (output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: summary[k] for k in ('status','error','rows_processed','means_ms','max_total_ms','policy_counts','phase_scores')}, indent=2))
    print(f'Results saved: {output}')
    return 130 if status == 'interrupted' else 1 if status == 'failed' else 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--engine', choices=['project','standalone'], default='project')
    p.add_argument('--dataset', default='elec2')
    p.add_argument('--csv', type=Path)
    p.add_argument('--features', help='comma-separated numeric columns for a custom CSV')
    p.add_argument('--target')
    p.add_argument('--positive', default='1'); p.add_argument('--negative', default='0')
    p.add_argument('--limit', type=int); p.add_argument('--warmup', type=int)
    p.add_argument('--shift-features', help='comma-separated columns; defaults to dataset-specific sensor/price inputs')
    p.add_argument('--scale', type=float, default=10)
    p.add_argument('--noise-fraction', type=float, default=.4); p.add_argument('--noise-window', type=int, default=500)
    p.add_argument('--max-latency-ms', type=float, default=15)
    p.add_argument('--accuracy-floor', type=float, default=.7); p.add_argument('--accuracy-window', type=int, default=500)
    p.add_argument('--cooldown', type=int, default=500); p.add_argument('--max-ram-growth-mb', type=float, default=512)
    p.add_argument('--seed', type=int, default=42); p.add_argument('--log-every', type=int, default=1)
    p.add_argument('--clean', action='store_true', help='control: disable feature shift and label corruption')
    p.add_argument('--fault-latency-ms', type=float, default=0, help='explicit artificial preprocessing delay to exercise R2')
    p.add_argument('--fault-rows', type=int, default=1)
    p.add_argument('--output', type=Path, default=ROOT/'results'/'stress')
    args = p.parse_args()
    for key in ('scale','max_latency_ms','max_ram_growth_mb'):
        if not math.isfinite(getattr(args,key)) or getattr(args,key) <= 0:
            p.error(f'{key} must be finite and positive')
    for key in ('noise_fraction','accuracy_floor'):
        if not 0 <= getattr(args,key) <= 1:
            p.error(f'{key} must be in [0,1]')
    for key in ('noise_window','accuracy_window','cooldown','log_every','fault_rows'):
        if getattr(args,key) < 1: p.error(f'{key} must be positive')
    if not math.isfinite(args.fault_latency_ms) or not 0 <= args.fault_latency_ms <= 1000:
        p.error('fault latency must be finite and between 0 and 1000 ms')
    try:
        return run(args)
    except (ImportError, OSError, ValueError, StopIteration) as exc:
        print(f'Cannot start: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
