#!/usr/bin/env python3
"""Launch three identical seeded replays concurrently and save matplotlib plots.

Concurrent timings include scheduler/CPU contention. This is a demonstration,
not an isolated-device benchmark or statistical superiority claim.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
POLICIES = {'static': 'A · Static', 'drift': 'B · Drift-only', 'unified': 'Unified controller'}
COLORS = {'static': '#64748b', 'drift': '#d97706', 'unified': '#007f86'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasets', nargs='+', default=['elec2', 'occupancy'])
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--reuse', type=Path, help='Regenerate plots from an existing comparison.json without rerunning models')
    parser.add_argument('--fault-latency-ms', type=float, default=0)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = ROOT / 'docs' / 'assets' / f'controller-comparison-{stamp}'
    if args.reuse:
        previous = json.loads(args.reuse.read_text())
        args.seed = previous['seed']
        args.fault_latency_ms = previous['fault_latency_ms']
        args.datasets = list(dict.fromkeys(k.split('/')[0] for k in previous['runs']))
        destination = args.reuse.resolve().parent
    destination.mkdir(parents=True, exist_ok=True)
    raw = ROOT / 'results' / 'controller-comparison' / stamp
    if args.reuse:
        raw = Path(next(iter(previous['runs'].values()))['summary_path']).parents[3]
    raw.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(raw / 'matplotlib-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    report = {'execution': 'Three concurrent subprocesses per dataset; datasets run sequentially',
              'seed': args.seed, 'fault_latency_ms': args.fault_latency_ms,
              'caveat': 'Shared-machine latency; one seed, no confidence intervals. No claim of superiority.',
              'policies': POLICIES, 'runs': {}}
    for dataset in args.datasets:
        if not args.reuse:
            running = {}
            # Start every worker before waiting on any worker.
            for policy in POLICIES:
                log = (raw / f'{dataset}-{policy}.log').open('w')
                command = [sys.executable, str(ROOT/'stress_test_mvp.py'), '--dataset', dataset,
                           '--policy', policy, '--seed', str(args.seed), '--log-every', '10000',
                           '--output', str(raw/dataset/policy), '--fault-latency-ms', str(args.fault_latency_ms)]
                running[policy] = (subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT), log)
            failures = []
            for policy, (process, log) in running.items():
                code = process.wait()
                log.close()
                if code:
                    failures.append(f'{dataset}/{policy}: exit {code}; see {raw}')
            if failures:
                raise RuntimeError('; '.join(failures))
        data, summaries = {}, {}
        for policy in POLICIES:
            folder = next((raw/dataset/policy).iterdir())
            summary = json.loads((folder/'summary.json').read_text())
            with (folder/'iterations.csv').open() as handle:
                records = list(csv.DictReader(handle))
            data[policy], summaries[policy] = records, summary
            assert len(records) == summary['rows_requested']
            assert sum(r['label_flipped'] == 'True' for r in records) == 200
        # Every method sees the same order and corrupted labels, with identical warm-up.
        reference = data['static']
        for policy in ('drift', 'unified'):
            assert [(r['index'], r['y_observed'], r['label_flipped']) for r in data[policy]] == [(r['index'], r['y_observed'], r['label_flipped']) for r in reference]
            assert summaries[policy]['source']['sha256'] == summaries['static']['source']['sha256']
        start = summaries['static']['bomb_index']
        warmup = summaries['static']['warmup']
        fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True, constrained_layout=True)
        for policy, records in data.items():
            x = np.arange(warmup, len(records))
            for axis, target in zip(axes[:2], ('y_observed', 'y_clean')):
                correct = np.array([int(r['prediction'] == r[target]) for r in records[warmup:]])
                rolling = np.convolve(correct, np.ones(500)/500, mode='valid') * 100
                axis.plot(x[499:], rolling, label=POLICIES[policy], color=COLORS[policy], lw=1.6)
            latencies = np.array([float(r['C_total_ms']) for r in records[warmup:]])
            blocks = [latencies[j:j+250] for j in range(0, len(latencies), 250)]
            bx = [warmup+min(j+249, len(latencies)-1) for j in range(0, len(latencies), 250)]
            axes[2].plot(bx, [np.percentile(b, 95) for b in blocks], color=COLORS[policy], label=POLICIES[policy], lw=1.6)
            full_latencies = np.array([float(r['C_total_ms']) for r in records])
            spike_indices = np.flatnonzero(full_latencies > 15)
            axes[2].scatter(spike_indices, full_latencies[spike_indices], color=COLORS[policy], marker='x', s=35)
            report['runs'][f'{dataset}/{policy}'] = {
                'summary_path': str(next((raw/dataset/policy).iterdir())/'summary.json'),
                'rows': len(records), 'source_sha256': summaries[policy]['source']['sha256'],
                'phase_scores': summaries[policy]['phase_scores'], 'policy_counts': summaries[policy]['policy_counts'],
                'mean_ms': float(np.mean(latencies)), 'p99_ms': float(np.percentile(latencies, 99)),
                'max_ms': float(np.max(latencies)), 'deadline_misses_after_warmup': int(sum(latencies > 15)),
                'deadline_misses_full_run': int(sum(full_latencies > 15)),
            }
        axes[0].set_title(f'{dataset.upper()} · identical data bomb, three concurrent policies', loc='left', fontsize=17, weight='bold')
        axes[0].set_ylabel('Observed-label accuracy\n500-row rolling %')
        axes[1].set_ylabel('Original-label accuracy\n500-row rolling %')
        for axis in axes[:2]:
            axis.axhline(70, color='#94a3b8', ls=':', lw=1)
            axis.set_ylim(0, 102)
        axes[2].set_ylabel('Service latency (ms)\np95 per 250 rows; × spikes (incl. warm-up)')
        axes[2].set_yscale('log')
        axes[2].axhline(15, color='#dc2626', ls='--', lw=1, label='15 ms budget')
        axes[2].set_xlabel('Stream row (zero-based)')
        for axis in axes:
            axis.axvline(start, color='#334155', ls='--', lw=1)
            axis.axvspan(start, start+500, color='#dc2626', alpha=.09)
            axis.grid(alpha=.18)
        axes[0].legend(loc='lower left', ncol=3, fontsize=10)
        axes[2].legend(loc='lower left', ncol=4, fontsize=9)
        fig.suptitle(f'10× feature shift persists after midpoint · 40% label flips in shaded 500-row window\nSeed {args.seed} · shared-MacBook timing · original labels used only by evaluator', fontsize=11)
        for suffix in ('png', 'svg'):
            fig.savefig(destination/f'{dataset}-accuracy-latency.{suffix}', dpi=200)
        plt.close(fig)
        print(f'{dataset}: three runs completed; plots saved in {destination}', flush=True)
    (destination/'comparison.json').write_text(json.dumps(report, indent=2)+'\n')
    lines=['# Controller comparison', '', report['execution']+'. '+report['caveat'], '',
           '| Dataset / policy | Before accuracy | Corrupted-window accuracy | After accuracy | Mean ms | p99 ms | Misses after warm-up / full run |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name, run in report['runs'].items():
        scores=run['phase_scores']
        values=[f"{scores[p]['observed_accuracy']:.2%}" for p in ('before','noise_window','after')]
        lines.append(f"| {name} | {' | '.join(values)} | {run['mean_ms']:.5f} | {run['p99_ms']:.5f} | {run['deadline_misses_after_warmup']} / {run['deadline_misses_full_run']} |")
    lines += ['', 'Mean/p99 latency metrics exclude warm-up. Spike markers and full-run miss counts include warm-up. Warm-up spikes triggered feature reductions in the unified runs, influencing their later trajectories; this comparison does not isolate post-drift resource effects. A prediction of the original label is wrong against a flipped label, so noise-window accuracy must be interpreted with original-label scores in the plots.', '', 'No artificial latency fault is enabled unless explicitly requested. Static freezes after warm-up. Drift-only keeps learning with ADWIN resets. Unified adds the shared latency/accuracy controller. All start with the same model, preprocessing, features and seed.', '', f'Fault setting: {args.fault_latency_ms} ms. Raw evidence: {raw}', '', 'Implemented paper subset: R1 drift response, R3 feature reduction, R4 accuracy refresh. Resource-gated R1/R4 and R2/R5 are not claimed.']
    for dataset in args.datasets:
        lines += ['',f'![{dataset} timelines]({dataset}-accuracy-latency.png)']
    (destination/'README.md').write_text('\n'.join(lines)+'\n')
    print(destination)


if __name__ == '__main__':
    main()
