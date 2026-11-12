# Phase 7 — run the testbed on a real device (optional)

Every budgeted result in the project so far is **simulated**: the limits are enforced in software on
a laptop. This kit runs the same trials on a real small device, such as a Raspberry Pi, and brings
the results back in the same bundle format, so the Studio shows them next to the simulated ones.

The project is complete without this step. Do it if a device is available and you want to replace
"simulated device limits" with a measurement.

**Status: the kit has been rehearsed on the development laptop only. It has not been run on a
Raspberry Pi.** See "What has and has not been checked" below.

## What you need

- A Raspberry Pi 4 or 5 (2 GB RAM or more) with **64-bit** Raspberry Pi OS, Bookworm or later
  (Python 3.11+). A 32-bit system will not work.
- About 3 GB free on the SD card, and a network connection for the one-time setup.
- A heatsink or fan if you have one. A hot Pi slows itself down, which changes the timings.

## Steps

**1. On the laptop: pack the kit.** Code plus the prepared dataset, in one file (about 1.1 GB of data
before compression).

```bash
research_testbed/device/pack.sh
```

**2. Copy it to the device and unpack it.**

```bash
scp research_testbed/device/out/adaptiveml-device-kit.tar.gz pi@raspberrypi.local:~
```

```bash
mkdir adaptiveml && tar -xzf adaptiveml-device-kit.tar.gz -C adaptiveml && cd adaptiveml
```

**3. On the device: set up once.** Creates a Python environment and checks the device and dataset.

```bash
bash research_testbed/device/setup.sh
```

If `pip` starts compiling River from source, the device has no ready-made package for it. Install the
build tools (`sudo apt install build-essential rustc cargo python3-dev`) and run the setup again; the
build can take a long time on a Pi.

**4. On the device: run.** Start with the quick run. Close other programs first.

```bash
backend/.venv/bin/python research_testbed/device/run_on_device.py --quick
```

Then the full run (300,000 connections; add `--seeds 11,23,37` for three repeats):

```bash
backend/.venv/bin/python research_testbed/device/run_on_device.py
```

It prints a summary table and the path of one results file, `device-<date>-<time>.tar.gz`, in
`research_testbed/device/out/`.

**5. Back on the laptop: import the results file.**

```bash
scp pi@raspberrypi.local:~/adaptiveml/research_testbed/device/out/device-*.tar.gz .
```

```bash
backend/.venv/bin/python research_testbed/device/import_bundle.py device-<date>-<time>.tar.gz
```

Open the Studio → **Testbed → Real device**. Device runs carry a "measured on Raspberry Pi …" tag.

## What the run does

1. **Records the device**: board model, CPU, memory, CPU governor, temperature before and after.
2. **Calibrates the cost model on the device.** The effort controller decides from a model of what
   each pipeline step costs. The laptop's numbers would be wrong on a slower processor, so they are
   measured again here, on Tuesday's traffic (not the rows used for the results).
3. **Sets two time budgets from that measurement.** On the laptop, the simulated tiers allow 100 and
   50 µs per connection, where the calibration run cost 80 µs. The device budgets keep the same
   ratios (1.25× and 0.62× the device's own calibrated cost), so "small" and "micro" are as tight on
   the device as they were on the laptop. Memory budgets are the same as the simulated tiers
   (8 MiB and 1 MiB).
4. **Runs the trials**, one at a time, each in a fresh process: copying the last label, incremental
   and adaptive learning without a budget; then the review's rules (R1–R5) and the effort controller
   under both budgets.
5. **Packs the bundle**: the runs, the calibration, a device record and a summary table.

## How to read the result honestly

- The **timings are real** for that device. That is what the simulation could not give.
- The **budgets are still placeholders**: they come from a rule, not from what an application needs.
  A real requirement would be "this gateway sees N connections per second".
- **Energy is not measured.** Do not quote energy figures.
- One device, one dataset, one slice. With one seed it is a single measurement, not a statistic.
- If the temperature after the run is above about 80 °C, the Pi probably slowed itself down. Add
  cooling and run again.
- For steadier timings, set the CPU governor to `performance` before the run
  (`sudo cpufreq-set -g performance`, from the `cpufrequtils` package). The run notes the governor it
  found.

## What has and has not been checked

- **Checked:** the whole chain (calibrate → budgets → trials → bundle → import → shown in the Studio)
  on the development laptop, as a *rehearsal*. A machine that does not name itself as a single-board
  computer is marked "rehearsal, not a device", and its budgets stay marked as simulated.
- **Not checked:** installation and running on an actual Raspberry Pi. In particular, whether `pip`
  finds a ready-made River package for the Pi, and how long the full run takes there (expect several
  times longer than the laptop).
