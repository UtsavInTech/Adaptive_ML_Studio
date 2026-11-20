"""The words, tables and figures of the project report.

Block types (see build.py for how each is drawn):
  ("h2", text) ("h3", text) ("p", text) ("pl", lead, text) ("bul", items) ("num", items)
  ("table", key, caption, header, rows, widths, opts) ("fig", key, file, width_in, caption)
  ("eq", text, number)
Inline: **bold**, *italic*, [[ref_key, ref_key]] for citations, <<tab:key>> and <<fig:key>> for
cross-references. Numbers in the results chapter are read from the saved result tables.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "research_testbed" / "reports"

META = {
    "title_main": "Adaptive ML Studio",
    "title_sub": "Cross-Scale Adaptive Machine Learning for Accuracy Stability Under Varying Data Conditions",
    "full_title": "Adaptive ML Studio: Cross-Scale Adaptive Machine Learning for Accuracy Stability Under Varying Data Conditions",
    "students": [("Simran Shikha", "2023431909"), ("Utsav Kumar", "2023430537"), ("Aastha Bansal", "2023230692")],
    "guide": "Dr. Neha Kumari",
    "guide_title": "Assistant Professor",
    "hod": "Prof. (Dr.) Jayant Shekhar",
    "month": "NOVEMBER, 2026",
}

ABSTRACT = [
    "A model that is trained once and then left alone gets worse when the data it sees begins to change. "
    "Ways of keeping a model up to date do exist, but most of them are judged on accuracy alone, although on a "
    "small device such as a router the time and memory a method uses matter just as much. The review paper we wrote "
    "earlier in this project (Paper 159) looked at 20 studies and pointed at this gap. It proposed five decision rules "
    "for adapting to changing data and to limited resources together, and it said plainly that the rules had not been "
    "tested. This project tests them.",
    "We built Adaptive ML Studio, a web application with a live demonstration, an experiment runner and a research "
    "testbed. The testbed replays 2.1 million real network connections from one week of the corrected CIC-IDS2017 "
    "data, with 22 dated attack periods, on simulated small devices that have a time and memory budget. Copying the "
    "previous answer is right 98.7% of the time on this stream, so accuracy cannot rank methods; the gain over copying "
    "(κ-temporal) can. Preparing the data and updating the model take most of the time per connection, while drift "
    "detection is cheap. The review's rules keep their quality but ran 42 to 94% over the time budget on the days we "
    "held out. A new controller that puts a price on computing time stayed at or near the budget, with equal or fewer "
    "wrong decisions, on Thursday and Friday, two days that were not used to design it. It fails when the true answers "
    "arrive late, and we report that failure. The devices are simulated and one dataset was used. The system passes "
    "175 backend and 54 frontend tests.",
]

ACK = (
    "A final year project teaches things that no lecture does, and we are grateful to the people who helped us through "
    "it. We thank the Head of the Department of Computer Science & Engineering, Sharda School of Engineering and "
    "Technology, for letting us take up this work. We are most thankful to our supervisor, Dr. Neha Kumari. She read "
    "our drafts more than once, asked the questions we had been avoiding, and stayed patient when an experiment gave "
    "an answer we did not want. Her guidance shaped both the review paper and this project. We also thank the faculty "
    "who taught us the machine learning and software engineering we used here, the researchers whose papers we cite, "
    "and the open-source communities behind River, FastAPI, React, NumPy and SciPy. Last, we thank our families and "
    "friends for putting up with the long evenings."
)

ABBREVIATIONS = [
    ("ADWIN", "Adaptive Windowing (a drift detector)"),
    ("API", "Application Programming Interface"),
    ("ARF", "Adaptive Random Forest"),
    ("CIC-IDS2017", "Canadian Institute for Cybersecurity intrusion detection dataset, 2017"),
    ("CPU", "Central Processing Unit"),
    ("CSV", "Comma-Separated Values"),
    ("DoS", "Denial of Service"),
    ("IoT", "Internet of Things"),
    ("JSON", "JavaScript Object Notation"),
    ("κ-temporal", "Kappa-temporal: gain over repeating the previous label"),
    ("µs", "Microsecond, one millionth of a second"),
    ("R1 to R5", "The five decision rules proposed in the review"),
    ("REST", "Representational State Transfer"),
    ("SRP", "Streaming Random Patches"),
    ("SSE", "Server-Sent Events"),
    ("UI", "User Interface"),
    ("YAML", "A plain-text settings file format"),
]


# ---------------------------------------------------------------- numbers from the saved tables
def _settings(name):
    with (REPORTS / name / "tables" / "settings.csv").open() as f:
        return list(csv.DictReader(f))


def _pick(rows, **kw):
    return next(r for r in rows if all(r[k] == v for k, v in kw.items()))


def _minus(s):
    return s.replace("-", "−")


def _k(r):
    k = float(r["kappa_temporal"])
    if abs(k) < 1e-9:
        return "0.00"
    return _minus(f"{k:.2f} [{float(r['kappa_temporal_low']):.2f}, {float(r['kappa_temporal_high']):.2f}]")


def whole_week_rows():
    rows = _settings("phase2")
    out = []
    for m, label in (("no_change", "Repeat last label"), ("static", "Static (trained once)"), ("incremental", "Incremental"),
                     ("adaptive", "Adaptive pipeline"), ("lev_bag", "Leveraging bagging"), ("arf", "Adaptive Random Forest"),
                     ("srp", "Streaming Random Patches")):
        r = _pick(rows, method=m, tier="standard")
        out.append([label, f"{float(r['accuracy']) * 100:.2f}", _k(r), f"{float(r['recall']) * 100:.1f}",
                    f"{float(r['false_alarm_rate']) * 100:.2f}", f"{float(r['mean_us']):,.0f}"])
    return out


def rules_vs_effort_rows():
    eff, held = _settings("effort"), _settings("heldout")

    def row(label, src, setting, tier, paired):
        j, e = _pick(src, setting=setting, method="joint", tier=tier), _pick(src, setting=setting, method="effort", tier=tier)
        return [label, f"{float(j['errors']):,.0f}", f"{float(e['errors']):,.0f}", paired,
                f"{float(j['mean_us']):.0f} to {float(e['mean_us']):.0f}"]

    return [
        row("Wednesday, small (design day)", eff, "core", "small_sim", "see the text"),
        row("Wednesday, micro (design day)", eff, "core", "micro_sim", "see the text"),
        row("Thursday, small", held, "thursday", "small_sim", "+50 [−139, +282]"),
        row("Friday, small", held, "friday", "small_sim", "−326 [−683, +1]"),
        row("Thursday, micro", held, "thursday", "micro_sim", "fewer in 2 of 3 runs, tie in 1"),
        row("Friday, micro", held, "friday", "micro_sim", "fewer in 2 of 3 runs, tie in 1"),
    ]


# ---------------------------------------------------------------- chapters
CH1 = [
    ("h2", "1.1 Problem Statement"),
    ("p", "Most machine-learning models are trained once, on data from the past, and then put to work. That is fine as "
          "long as the world stays still, and it rarely does. Customers change their habits, sensors wear out, and "
          "attackers try new methods. When the link between the inputs and the correct answer shifts in this way, it is "
          "called concept drift. A model trained before the shift goes on giving confident answers that are no longer "
          "right."),
    ("p", "There are good techniques for following such changes while data keeps arriving: scaling can be updated as new "
          "values come in, useful inputs can be picked on the fly, a change can be detected, and a model can learn one "
          "example at a time. When we reviewed twenty studies of these techniques we found that they are mostly studied "
          "one at a time and mostly judged on accuracy. On a router or an IoT gateway accuracy is only half of the story, "
          "because such a device has little processing time and memory, and every update takes a share of both."),
    ("p", "The problem we took up has two parts. The first is about measurement. How can a complete adaptive pipeline be "
          "run on a changing stream so that its accuracy and the cost of every stage are recorded together, in a way that "
          "another person can repeat? The second is about decisions. When changing data and a limited budget both "
          "matter, how much work should the pipeline do on each incoming item? Our review proposed five rules for this "
          "and said openly that they had not been tested. We wanted to find out whether they work."),
    ("h2", "1.2 Project Overview"),
    ("p", "The project has three connected pieces. The first is the review paper, “Adaptive Machine Learning Pipelines for "
          "Evolving Data Streams: A Comprehensive Review” (Paper 159), which surveys 20 studies and ends with a proposal "
          "[[paper159]]. The second is Adaptive ML Studio, the web application we built to run the proposed pipeline and "
          "measure it: a live demonstration, an experiment runner and a research testbed that replays a week of real network "
          "traffic. The third is a new controller, designed after the testbed showed where the review's rules fall short."),
    ("p", "The work has five objectives:"),
    ("num", [
        "To build one pipeline that covers adaptive preprocessing, feature selection, drift detection, model adaptation and "
        "prediction, and to time every stage in the same run so that a run can be repeated.",
        "To bring a large real dataset into the platform without loading all of it into memory.",
        "To score methods fairly on streams, with a copy-the-last-answer baseline and a gain measure called κ-temporal.",
        "To turn the review's five decision rules into a working controller and test them under simulated device limits.",
        "To design a better controller from what the tests show, and to check it on days not used in its design.",
    ]),
    ("h2", "1.3 Expected Outcome"),
    ("p", "We expected a working platform that someone else can start with two commands, and saved results that can be run "
          "again. We expected to learn which of the review's rules hold up on real traffic and where the time per connection "
          "goes, and we hoped, without being sure, that a better controller could be built. What we did not expect was that "
          "late labels would break both controllers; Section 4.2.5 describes it."),
    ("h2", "1.4 Hardware & Software Specifications"),
    ("table", "hw", "Hardware and software used", ["Item", "Specification"], [
        ["Machine", "Laptop with an Apple M1 chip, 8 GB of memory and about 3 GB of disk used. All timings in this report come from it."],
        ["Language and runtime", "Python 3.11 for the backend; Node.js 24 for the frontend tools."],
        ["Stream learning", "River 0.26.1 (Hoeffding tree, ADWIN, Adaptive Random Forest, Streaming Random Patches) [[montiel2021]]."],
        ["Backend and frontend", "FastAPI, Pydantic, NumPy and SciPy; React 19, TypeScript and Vite; Matplotlib for report figures."],
        ["Testing and files", "pytest and Vitest; plain JSON, CSV and YAML result files; no database, no GPU."],
    ], [2300, 6700], {"size": 20}),
    ("h2", "1.5 Other Non-Functional Requirements"),
    ("bul", [
        ("Reproducibility:", "every run saves its settings, seed, data checksum and machine details, so it can be run again "
                             "and compared by the hash of its predictions."),
        ("Honest labelling:", "every number says whether it was measured or simulated, and every simulated device is marked "
                              "as having placeholder budgets."),
        ("Isolation:", "each trial runs alone in a fresh process and only one job runs at a time, so one method's cost "
                       "cannot leak into another's timing."),
    ]),
    ("h2", "1.6 Report Outline"),
    ("p", "Chapter 2 reviews earlier work and describes the proposed system. Chapter 3 is the technical core. Chapter 4 shows "
          "the application and what the experiments found, including what went wrong. Chapter 5 concludes, and Chapter 6 lists "
          "the references. Annexure I records the evaluation meetings and Annexure II holds the evidence for the paper."),
]

CH2 = [
    ("h2", "2.1 Existing Work"),
    ("p", "A data stream is a sequence of items that arrives over time, too fast and for too long to be stored and visited "
          "again. A model that learns from a stream has to update itself one item at a time, and the usual way to test it "
          "is to let it predict each item first and only then show it the true answer. This test-then-learn scheme, called "
          "prequential evaluation, is used throughout. Gama and "
          "colleagues [[gama2014]] sorted the ways data can change into sudden, gradual, incremental and recurring drift, "
          "and our Live demo offers the same four. A drift detector watches a signal, often the model's own error "
          "rate, and raises an alarm when it changes; ADWIN [[bifet2007]] uses a window that shrinks when its average shifts."),
    ("p", "For the learner, the common choice on streams is the Hoeffding tree [[domingos2000]], which splits a node only when "
          "enough examples have been seen to be sure of the best split. Ensembles of such trees, among them "
          "Adaptive Random Forest [[gomes2017]], Streaming Random Patches [[gomes2019]] and Leveraging Bagging, "
          "are more accurate and a good deal slower, because every member learns from every item. The last piece of "
          "background is how streams should be scored. In many streams the label of one item is likely to equal the label "
          "of the one before it. Žliobaitė and colleagues [[zliobaite2015]] showed that on such streams accuracy flatters "
          "any method, and proposed κ-temporal, which compares a method with the one that just repeats the previous label."),
    ("h2", "2.2 Related Work"),
    ("p", "Libraries such as River [[montiel2021]] give researchers the building blocks of stream learning. They leave "
          "open how much work a pipeline should do on each item while it runs, and they do not split the cost of a run by stage. Drift-aware methods concentrate on noticing a change quickly and "
          "recovering from it, and are judged mainly on accuracy and detection delay. Adaptive preprocessing and feature "
          "selection were studied on their own, usually without counting their cost."),
    ("p", "A second line of work takes resources seriously. Petri and colleagues [[petri2022]] studied resource-aware stream "
          "analytics at the edge, Disabato and Roveri [[disabato2024]] handled concept drift on very small devices, and "
          "Lourenço and colleagues [[lourenco2026]] proposed DFDT, a decision tree that limits its memory for IoT devices. "
          "The closest work we found is RCCDA by Piaseczny and colleagues [[piaseczny2025]]. It decides when to update a "
          "model so that an average resource budget is respected. That is one yes-or-no choice under an average budget; it "
          "says nothing about the deadline for a single item, a memory limit, or the stages of a pipeline. <<tab:lit>> "
          "lists the studies that matter most here."),
    ("table", "lit", "Literature survey", ["Study", "Year", "What it contributes", "What it leaves open"], [
        ["Bifet and Gavaldà (ADWIN) [[bifet2007]]", "2007", "Drift detection with a window that adapts its own length",
         "Cost of detection not reported by stage"],
        ["Žliobaitė et al. [[zliobaite2015]]", "2015", "Scoring for streams with temporal dependence (κ-temporal)",
         "Defines the score only; says nothing about cost"],
        ["Gomes et al. (ARF) [[gomes2017]]", "2017", "Ensemble with a drift detector in every tree",
         "Accurate, but several times slower per item"],
        ["Petri et al. [[petri2022]]", "2022", "Resource-aware stream analytics at the edge", "Drift response not tied to the budget"],
        ["Piaseczny et al. (RCCDA) [[piaseczny2025]]", "2025", "Decides when to update under an average resource budget",
         "One yes-or-no choice; no deadline, memory limit or stages"],
        ["Lourenço et al. (DFDT) [[lourenco2026]]", "2026", "Memory-limited decision tree for IoT devices",
         "66.7% accuracy at 244.9 µs per item in its own setting; not comparable"],
    ], [2350, 600, 3050, 3000], {"size": 18, "align": "llll"}),
    ("h2", "2.3 Proposed System"),
    ("p", "The review ended with a proposal: a stream monitor and a resource monitor feed one controller. Five rules turn "
          "the readings into actions, and the choice of configuration is written as minimising "
          "J = α(1 − A) + βL + γC + δM + εE, where A is accuracy, L latency, C computing cost, M memory and E energy "
          "[[paper159]]. The review called this a research direction and did not validate it. Adaptive ML Studio is our system "
          "for testing it, with six modules:"),
    ("bul", [
        ("M1 Data layer:", "catalogue with checksums, row-by-row reader, label delay settings."),
        ("M2 Pipeline:", "preprocessing, selection, prediction, drift detection, learning."),
        ("M3 Controllers:", "the review's rules R1 to R5 and the new effort controller."),
        ("M4 Metrics:", "accuracy, κ-temporal, per-attack results, cost terms, intervals."),
        ("M5 Runner:", "one fresh process per trial, saved bundles, report generator."),
        ("M6 Interface:", "six pages, from Home to Method."),
    ]),
    ("p", "To our knowledge no earlier study joins a whole pipeline, a per-item budget, late labels and a fair score on a real "
          "stream. We say “to our knowledge” because we could only check the literature we found; our confidence is medium."),
    ("h2", "2.4 Feasibility Study"),
    ("pl", "Technical and economic feasibility.", "Everything runs on one laptop with free, open-source software, and memory stays at "
                                                  "about 150 to 165 MB per trial because the large dataset is read one row at a time."),
    ("pl", "Operational feasibility.", "The system starts with two commands, and results are saved as plain files that anyone can open."),
]

CH3 = [
    ("h2", "3.1 Project Perspective"),
    ("p", "Three things shaped how we worked: the development model, the skills the work needed, and who did what."),
    ("h3", "3.1.1 Development model"),
    ("p", "We followed an iterative and incremental model. The system is made of parts that can be built and tested one at a "
          "time, and each result decided what to build next. <<tab:phases>> lists the phases in the order we did them."),
    ("table", "phases", "Development phases", ["Phase", "What was built", "How it was checked"], [
        ["0  Review", "Survey of 20 studies, gap analysis, rules R1 to R5", "Paper 159 (Annexure II)"],
        ["1  Studio", "Per-row pipeline with stage timers, live demo, experiment runner", "Stage times add up to row time"],
        ["2  Real data", "Corrected CIC-IDS2017 preparation and row-by-row reader", "Checksums; flat memory"],
        ["3  Scoring", "Copy baseline, κ-temporal, per-attack results, cost terms", "Hand-computed test cases"],
        ["4  Controllers", "Rules R1 to R5 and the effort controller", "One test per rule and lever"],
        ["5  Scale", "Device tiers, late labels, protocol, report generator", "Label delay checked by tests"],
        ["6  Screens", "Testbed and Findings pages; kit for a Raspberry Pi", "Demo run from the page; kit rehearsed on a laptop"],
    ], [1500, 4500, 3000], {"size": 19}),
    ("h3", "3.1.2 Team responsibilities"),
    ("p", "The review and the project were shared among the three of us (<<tab:team>>). Dr. Neha Kumari supervised the work and "
          "is a co-author of the paper."),
    ("table", "team", "Team responsibilities", ["Member", "Responsibility"], [
        ["Simran Shikha", "Adaptive machine-learning pipeline, adaptive preprocessing, online feature selection, and the classification of the reviewed studies."],
        ["Utsav Kumar", "Concept drift detection, incremental learning and model adaptation in the review. Implementation of Adaptive ML Studio, the testbed and both controllers, and the experiments."],
        ["Aastha Bansal", "Edge-deployment considerations, performance monitoring, comparative analysis, system architecture and documentation."],
    ], [2000, 7000], {"size": 21}),
    ("h2", "3.2 Performance Requirements"),
    ("p", "The system had to keep timings honest and memory flat. Each trial runs alone in a fresh process, only one job is "
          "accepted at a time, and the large stream is never loaded whole: reading all 2.1 million rows takes about 28 seconds "
          "and 89 MB, and a full-week trial peaks at 150 to 165 MB. For the controllers the requirement was different. The "
          "mean time per connection should stay at or near the budget of the chosen device (100 µs for the small device, "
          "50 µs for the micro device), and the model should stay under the device's memory limit."),
    ("h2", "3.3 System Features"),
    ("table", "fr", "Functional requirements", ["ID", "Requirement", "Specification"], [
        ["FR1", "Live demonstration", "Replay a small dataset row by row with one added change (sudden, gradual, incremental or recurring); show a model trained once against one that keeps learning."],
        ["FR2", "Experiment runner", "Run methods and seeds from one settings file, each trial in its own process; save settings, seed, checksum and machine; re-run and compare prediction hashes."],
        ["FR3", "Large stream, late labels", "Read the 2.1-million-row dataset one row at a time, with start row, length, arrival rate, label delay and label coverage as settings."],
        ["FR4", "Fair scoring and cost", "Accuracy, macro-F1, attack recall, false alarms, κ-temporal, results per attack type and period, intervals, and the time of each pipeline stage."],
        ["FR5", "Device tiers", "Simulated limits on time per row, deadline and model memory, enforced in software."],
        ["FR6", "Controllers", "The review's rules R1 to R5, each one switchable, and the effort controller."],
        ["FR7", "Screens and reports", "Six pages from Home to Method; a Testbed page that starts runs; a Findings page that reads saved reports."],
    ], [700, 2000, 6300], {"size": 19, "align": "lll"}),
    ("h2", "3.4 Methodology"),
    ("p", "<<fig:arch>> shows how the system is put together. A React application in the browser talks to a FastAPI server. The "
          "server does not do the learning itself. When a run starts it hands the settings to a trial worker, a separate "
          "process that holds the stream reader, the pipeline, the controller and the metrics, so the web server cannot "
          "disturb the timings."),
    ("fig", "arch", "fig_architecture.png", 3.4, "Overall system architecture"),
    ("h3", "3.4.1 Dataset"),
    ("p", "The main dataset is the corrected CIC-IDS2017 [[liu2022]], a repaired version of the original "
          "recording. It covers five days of network traffic in July 2017, with scripted attacks. There are 2,099,976 connections with 83 numeric inputs each, and 505,431 of them (24.1%) are attacks. The "
          "task is binary: attack or normal. The original day files are not in time order, so we wrote a preparation script "
          "that merges them into one stream ordered by the time each connection ended, which is the time a device could "
          "first score it. The script labels connections marked only as attempted attacks as normal, as the corrected "
          "release advises, and writes a schedule of the 22 dated attack periods. Three smaller datasets are also "
          "registered for the Live demo: electricity prices (ELEC2, 45,312 rows), room occupancy (20,560 rows) and a "
          "synthetic stream with a known change point."),
    ("h3", "3.4.2 Stream reader and preprocessing"),
    ("p", "A new reader streams the prepared file one row at a time, so memory stays flat however long the stream is. Each "
          "row is first prepared. A missing value is filled with the running mean, every input is standardised with a mean "
          "and variance that slowly forget old rows (fading factor 0.001), and values beyond five standard deviations are "
          "clipped. Input selection follows the truncation idea of online feature selection: a small online "
          "logistic regression ranks the inputs by the size of its weights, and the model keeps the top two thirds by "
          "default."),
    ("h3", "3.4.3 The adaptive pipeline"),
    ("p", "Every row takes the path in <<fig:pipe>>. The pipeline predicts first and learns afterwards, so a model is never "
          "scored on a row whose answer it has already seen. The learner is a Hoeffding tree with a grace period of 200 rows. "
          "ADWIN receives the model's 0-or-1 error on each row, with a warning level of 0.01 and an alarm level of 0.002, "
          "and an alarm is acted on only when the error rate has gone up. If a warning came first, a replacement model is "
          "trained in the background and swapped in after 200 rows of learning. If background models are not allowed, the "
          "model is reset at once. After any adaptation the pipeline waits 300 rows before acting again. Every stage sits "
          "between two timer readings, so the stage times add up to the time spent on the row."),
    ("fig", "pipe", "fig_pipeline.png", 4.0, "The per-row pipeline and the controller"),
    ("h3", "3.4.4 Scoring"),
    ("p", "Scores are computed after a warm-up of 1,000 rows. Besides accuracy we report macro-F1, attack recall and the "
          "false-alarm rate. Two further measures make the stream fair. The first is a baseline that ignores every input and "
          "repeats the previous label. The second is κ-temporal [[zliobaite2015]]:"),
    ("eq", "κ_{t} = (A − A_{copy}) / (1 − A_{copy})", 1),
    ("p", "where A is the accuracy of the method and A_{copy} the accuracy of the copy baseline. It is 0 when a method is no "
          "better than copying, 1 when it is perfect, and negative when it is worse. Neighbouring rows are not independent, "
          "so confidence intervals come from resampling blocks of 10,000 consecutive rows 1,000 times, and many methods are "
          "compared with the Friedman test and the Nemenyi critical difference [[demsar2006]]. The review defines the total "
          "adaptation cost as"),
    ("eq", "C_{total} = C_{pre} + C_{fs} + C_{drift} + C_{inf} + C_{upd} + C_{ret} + C_{comm}", 2),
    ("p", "that is, preprocessing, feature selection, drift detection, inference, model update, retraining and communication. "
          "We measure every term except C_{comm}, which does not apply because everything runs on one machine."),
    ("h3", "3.4.5 Simulated device tiers"),
    ("p", "A tier is a set of limits that a controller must respect (<<tab:tiers>>): a CPU budget per connection, a deadline "
          "for a single connection, and a limit on model memory. They are enforced in software on the laptop. No slower "
          "processor is imitated, so a budget of 100 µs is a share of this machine's time and not a measurement of a real "
          "device. The values are placeholders that we chose so that the limits bind for these methods, and every screen and "
          "report says so."),
    ("table", "tiers", "The simulated device tiers", ["Tier", "CPU per connection", "Deadline", "Model memory", "Other limits"], [
        ["standard", "none", "none", "none", "No limits; the reference"],
        ["small (Raspberry Pi class)", "100 µs", "0.5 ms", "8 MiB", "Updates may be thinned to every 4th row; at least 4 inputs"],
        ["micro (IoT gateway class)", "50 µs", "0.2 ms", "1 MiB", "No replacement model; updates at most every 8th row; at least 2 inputs"],
        ["memory only", "none", "none", "256 KiB", "Isolates the memory rule"],
    ], [2100, 1300, 1000, 1200, 3400], {"size": 19, "align": "lllll"}),
    ("h3", "3.4.6 The review's rules as a controller"),
    ("p", "The first controller turns the review's five rules into code (<<tab:rules>>). The review says that resource limits "
          "come first when rules conflict, and the order of checking follows that: the memory rule, then the deadline rule, "
          "then the rules for drift and accuracy. Each rule can be switched off for an ablation."),
    ("table", "rules", "The review's decision rules as implemented", ["Rule", "Condition", "Action"], [
        ["R1", "Drift confirmed and resources spare", "Train a replacement model in the background and swap it in when it is ready"],
        ["R2", "Drift confirmed and resources tight", "Adapt cheaply: reset the model at once"],
        ["R3", "Too many rows miss the deadline", "Halve the inputs, then process only the inputs in use, then learn from fewer rows; step back up when calm"],
        ["R4", "Accuracy below 70% and resources spare", "Retrain a fresh model on the last 2,000 labelled rows"],
        ["R5", "Model over its memory budget", "Drop the replacement model, then start a fresh model, then halve the inputs"],
    ], [700, 3100, 5200], {"size": 20, "align": "lll"}),
    ("h3", "3.4.7 The budgeted effort controller"),
    ("p", "The first results (Chapter 4) showed where the rules go wrong, and the effort controller is our answer. It keeps the "
          "same pipeline and the same hard limits, but instead of the rule “use fewer inputs first” it chooses how much work "
          "to do on each row (<<fig:ctrl>>). A level is a setting of five levers: prepare only the inputs the models need, "
          "update the scaler statistics on one row in a few, update the input ranking on one row in a few, skip the model "
          "update on easy rows, and change the number of inputs only after the ranking has seen enough of both classes."),
    ("fig", "ctrl", "fig_controller.png", 3.9, "The budgeted effort controller"),
    ("p", "Which level a row gets depends on an activity signal and on a price of compute. The activity signal is built from "
          "the recent rate of label changes, the recent error rate and drift alarms. The price rises when a row costs more "
          "than its share of the budget and falls when it costs less:"),
    ("eq", "λ ← min(5, max(0, λ + 0.002 (c / B − 1)))", 3),
    ("p", "where c is the cost of the row and B the budget per row. For each row the controller picks the level with the "
          "highest value of benefit × activity − λ × cost. To make its decisions repeatable, the controller reads a modelled "
          "cost and not a timer. The model adds up the work the pipeline did, with coefficients such as 212 ns per input "
          "prepared and 6,688 ns plus 935 ns per feature for a model update. We calibrated them on Tuesday's traffic, a day "
          "that is not used for any result."),
    ("h3", "3.4.8 Late and missing labels"),
    ("p", "In real use the true answer for a connection is not known at once. A label delay holds each label back for a "
          "number of rows, and a coverage setting lets only a share of rows ever get a label. Drift detection, adaptation and "
          "learning use only the labels that have arrived, while scores still use every row's true label, so they show what "
          "the late information costs."),
    ("h2", "3.5 Testing Process"),
    ("p", "We tested the parts where a silent mistake would corrupt a result. The backend has 175 automated tests and the "
          "frontend 54. They check the order and labelling rules of the data preparation, that the stage timers add up, that "
          "every rule of both controllers fires on a hand-built case, the statistics against SciPy and a worked example from "
          "Demšar's paper [[demsar2006]], and that the report server refuses paths outside the reports folder. Errors are "
          "meant to be loud: unknown keys in a settings file are rejected, and a checksum mismatch stops a run before "
          "anything is computed. A few older tests depend on timing "
          "and can fail when the laptop is heavily loaded. <<tab:status>> shows where each feature stands."),
    ("table", "status", "Implementation status", ["Task", "Status"], [
        ["Pipeline, stage timers, live demo, experiment runner", "Done"],
        ["Corrected CIC-IDS2017 preparation and stream reader", "Done"],
        ["Fair scoring and cost terms", "Done"],
        ["Device tiers, late and missing labels", "Done (placeholder budgets)"],
        ["Review's rules R1 to R5 and the effort controller", "Done"],
        ["Protocol, statistics and report generator", "Done; the full protocol of 333 trials was not run"],
        ["Testbed and Findings pages", "Done"],
        ["Run on a real Raspberry Pi; energy measurement", "Kit rehearsed on a laptop, not run on a device; energy not measured"],
    ], [5100, 3900], {"size": 19}),
]

CH4 = [
    ("h2", "4.1 Application Outputs"),
    ("p", "Adaptive ML Studio opens on a Home page (<<fig:home>>) that explains the problem before it shows any instrument. "
          "The curve is a recorded run of a model that keeps learning against one that was trained once and then frozen. "
          "The top bar is numbered 1 to 6 (Home, Live demo, Experiments, Testbed, Findings, Method) in the order the project "
          "is explained, and every page ends with a button to the next step."),
    ("fig", "home", "ui_home.png", 3.9, "Home page of Adaptive ML Studio"),
    ("p", "The Live demo replays a small dataset row by row. <<fig:live>> shows a finished run on the room occupancy data with a "
          "recurring change. The model that keeps learning made 176 wrong predictions out of 9,000 rows, against 628 for the "
          "model trained once (98.0% against 93.0% right). The panel counts over the whole run on purpose. In our first version the large "
          "figures described only the last 500 rows, and because the recurring change had ended by then, both models read "
          "close to 100% and the page seemed to show no difference at all. We changed the screen after seeing that ourselves."),
    ("fig", "live", "ui_live.png", 5.0, "Live demo: result of one finished run"),
    ("p", "The Testbed page starts a run on the real traffic. A button fills in a demonstration that takes about 40 seconds: "
          "40,000 connections that contain two real attacks, on the simulated small device. When the run finishes, its "
          "results page (<<fig:run>>) opens with three cards in plain words: the share of attacks caught, the false alarms, "
          "and the time per connection against the device's budget. The full table, the stage-by-stage cost and what each controller decided follow below. In this short run the new "
          "controller caught 95.5% of the attacks at 110 µs per connection and the review's rules 94.8% at 122 µs. We treat "
          "it as a demonstration of the screen, not as evidence; the evidence is in Section 4.2. The Findings page states the "
          "main result and four findings in plain words, reading its numbers from the saved reports."),
    ("fig", "run", "ui_run_plain.png", 5.6, "Results page of a testbed run"),
    ("h2", "4.2 Experimental Results"),
    ("p", "Every result below comes from a saved run. Timings are mean microseconds per connection, measured on one Apple M1 "
          "laptop, and the devices are simulated."),
    ("h3", "4.2.1 Accuracy cannot rank the methods"),
    ("p", "Over the whole week, repeating the previous label is right 98.70% of the time. Every method that keeps learning "
          "lands between 99.14 and 99.89%, so by accuracy they look alike (<<tab:week>>, <<fig:acc>>a). Scored by κ-temporal "
          "they separate clearly, from 0.34 for plain incremental learning to 0.92 for Streaming Random Patches "
          "(SRP; ARF is Adaptive Random Forest) in <<fig:acc>>b. The static model, which learned only from the first 1,000 connections (all normal Monday "
          "traffic), never flags an attack and scores −17.6. <<fig:time>> shows it over time: the static model "
          "collapses in every attack period. The price of the top scores is high: "
          "Streaming Random Patches takes about 38 times as long per connection as the adaptive pipeline (4,790 against "
          "125 µs) and Adaptive Random Forest about five times."),
    ("table", "week", "Methods compared over the whole week (2,099,976 connections)",
     ["Method", "Accuracy (%)", "κ-temporal [95% interval]", "Attacks caught (%)", "False alarms (%)", "µs per connection"],
     "WEEK", [2200, 1000, 2000, 1250, 1250, 1300], {"size": 19, "align": "lrrrrr", "keep": True}),
    ("fig", "acc", "fig_accuracy_vs_kappa.png", 5.2, "Accuracy and κ-temporal of the methods over the whole week"),
    ("fig", "time", "fig_timeline.png", 5.2, "Accuracy over the week; shaded bands are the dated attack periods with at least 100 flows"),
    ("h3", "4.2.2 Where the time goes"),
    ("p", "The review called it an open question which pipeline stage costs the most. <<fig:cost>> answers it for this software. "
          "In plain incremental learning, getting the data ready (scaling and choosing inputs) takes 67 of 164 µs and learning "
          "takes 85 µs, together 93% of the time; the prediction itself takes 12 µs. Checking for drift costs about 1 to 2% "
          "in the methods that do it. The new controller's bar is shorter because it spends less on exactly those two parts, "
          "30 and 35 µs, and its own decisions cost 8 µs. These shares hold for this Python and River implementation only."),
    ("fig", "cost", "fig_cost_terms.png", 4.6, "Where the time per connection goes on the simulated small device"),
    ("h3", "4.2.3 The review's rules against the new controller"),
    ("p", "Wednesday's traffic (300,000 connections, four dated attack periods) is the stretch the new controller was designed "
          "on, so it counts as a development result. Thursday and Friday played no part in the design, in calibrating the cost "
          "model (we used Tuesday for that) or in checking it, and we changed nothing after looking at them. <<tab:vs>> gives "
          "both, and <<fig:held>> shows the two held-out days."),
    ("table", "vs", "The review's rules (R1 to R5) against the new controller",
     ["Day, device", "Rules: errors", "New: errors", "Paired difference, new − rules [95% interval]", "µs per connection, rules to new"],
     "VS", [2300, 1050, 1000, 2900, 1750], {"size": 19, "align": "lrrll", "keep": True}),
    ("p", "On the small device the rules overshoot the 100 µs budget, running at 153 and 142 µs on Thursday and Friday (42 to "
          "53% over), while the new controller runs at 75 and 89 µs. Quality is the more modest part of the story. Thursday "
          "is a tie on the small device (+50 errors, interval spanning zero) and Friday favours the new controller by 326 "
          "errors, with an interval that only just touches zero. On the micro device the new controller "
          "meets the 50 µs budget on Thursday (48 µs) and runs 14% over it on Friday (57 µs), because the cost model "
          "under-predicts there; the rules run at 97 and 76 µs. The claim these data support is therefore “equal or fewer "
          "errors than the review's rules, at or near the budget, which the rules exceed”. On Wednesday the new controller "
          "made 27% fewer errors on the small device (1,660 against 2,275). A paired comparison on the same rows, in blocks "
          "of 10,000 connections, put the difference at −563 errors with a 95% interval of −966 to −148 (the rules "
          "controller reads a timer, so two runs of it differ a little). That is better than the held-out days suggest, as "
          "one would expect from the day a method was designed on. On the micro device the new controller met the budget "
          "(47 µs against 90 µs) but made 17% more errors (3,099 against 2,638), with an interval that spans zero."),
    ("fig", "held", "fig_heldout.png", 5.2, "Thursday and Friday: computing time against the device budget, and wrong decisions per day"),
    ("p", "The new controller is repeatable: three seeds gave identical predictions on every day and device. The rules "
          "controller is not: three runs on identical data made 2,389, 4,316 and 4,388 errors on the micro device on Thursday."),
    ("h3", "4.2.4 What each part is worth, and the memory rule"),
    ("p", "To see which parts of the new controller earn their place we removed them one at a time on the small device. Without "
          "the activity signal, the fast model switch, the price of compute, the skipping of updates on easy rows, the live "
          "feature ranking or the sampled scaler statistics, the errors rose by between 484 and 1,105; removing the other "
          "parts changed little. One result we cannot explain yet: skipping the model update on easy rows lowers the cost, as "
          "expected, and also lowers the errors. We guess that fewer updates keep the model steadier but have not tested it."),
    ("p", "At first the review's memory rule R5 never fired, because River's own size cap pruned the tree before the model "
          "reached the 2 MiB limit. With that cap switched off and a device tier that has only a 256 KiB limit, R5 kept the "
          "model within its limit at 99.1% of the memory checks over the whole week, against 54% without it, but κ-temporal "
          "fell from 0.75 to 0.57. Holding a memory limit costs detection quality."),
    ("h3", "4.2.5 When the true answers arrive late"),
    ("p", "This is the result that did not work. When every label arrives 1,000 connections late, both controllers do badly. "
          "On Wednesday's traffic the rules controller makes 60,387 errors and the new controller 56,712, while plain "
          "incremental learning, which never resets, makes 9,602. The saved runs showed that most of the rules controller's "
          "errors came shortly after its own model resets: the new model is blind for a thousand connections because its "
          "first labels have not arrived. Our first repair, which made the controller aware of the delay, made things worse "
          "(56,712 errors against 39,973 without it). Both are far from 9,602, so we report the problem as open."),
    ("h2", "4.3 Problems We Met"),
    ("p", "Not everything went as planned. <<tab:defects>> lists the defects that taught us the most."),
    ("table", "defects", "Defects found and how they were resolved", ["What went wrong", "How we found it", "What we did"], [
        ["Inputs were cut after the ranking had seen only normal traffic, so four poor inputs were kept for 2.1 million rows",
         "Analysis of a tight-budget run", "The effort controller ranks live and cuts only after both classes were seen"],
        ["The memory rule never fired", "The model was 52 KB against a 2 MiB limit",
         "Switched off River's size cap for the rules controller; added a memory-only tier"],
        ["The deadline rule and the memory rule undid each other's cuts", "A test run halved the inputs from 56 to 28 eight times",
         "The deadline rule now restores only its own cuts"],
        ["A server started before a new method existed rejected the demonstration run", "Running the demonstration from the page",
         "Restart the server after code changes; noted in the presentation guide"],
    ], [3600, 2500, 2900], {"size": 19, "align": "lll"}),
    ("h2", "4.4 Discussion and Limitations"),
    ("bul", [
        ("Accuracy hides almost everything on this stream.", "A method can look excellent while doing no better than copying. "
                                                           "Anyone reading a security paper on streams should ask what a method that repeats the last answer would score."),
        ("Cost is not where we expected it.", "Drift detection, which gets the literature's attention, is cheap; preparing the data and "
                                              "updating the model are what cost."),
        ("The review's rules work, with a catch.", "Under a real budget the rule that cuts inputs first overshoots a small "
                                                  "device, and its worst failures came from a timing flaw, not from the idea. That is why an untested proposal had to be tested."),
        ("The new controller helps, but less than Wednesday suggested.", "On the small device it matches or beats the rules in about half "
                                                                        "the time. The best methods from the literature stay well ahead on accuracy (Adaptive Random Forest makes 589 errors "
                                                                        "on Wednesday, at 1,368 µs per connection). The controller offers the best result inside a budget, not the best result."),
        ("The devices are simulated.", "Budgets are placeholders enforced in software, and no energy was measured. The Raspberry Pi "
                                      "kit was rehearsed on the laptop but has not been run on a device."),
        ("One dataset, one network, single runs.", "Thursday and Friday come from the same week and network as the design day, and "
                                                  "timings come from a shared laptop. The full protocol of 333 trials was not run."),
        ("Open problems.", "Late labels are unsolved, and the rarest attacks (Heartbleed with 11 connections, SQL injection with 13) "
                          "are missed by every method."),
    ]),
]

CH5 = [
    ("h2", "5.1 Conclusion"),
    ("p", "This project began with a review that ended in a proposal it could not test. We built Adaptive ML Studio to test it: "
          "a web application and a research testbed that replay 2.1 million real network connections, with 22 dated attack "
          "periods, through an adaptive pipeline under simulated device limits, recording accuracy and the cost of every stage "
          "together."),
    ("p", "The measurements taught us four things. Accuracy cannot rank methods on this stream, because copying the previous "
          "answer scores 98.7%; the gain over that copy, κ-temporal, can. Preparing the data and updating the model, and not "
          "drift detection, take most of the time per connection. The review's rules keep their quality but ran 42 to 94% "
          "over the time budget of the simulated devices on the days we held out. And a controller that puts a price on "
          "computing time stays at or near the budget with equal or fewer errors, in about half the time on the small "
          "device, although it is less accurate than the best ensembles from the literature."),
    ("p", "It did not work everywhere. When true answers arrive late, both controllers fail and plain incremental learning does "
          "far better. Our results come from simulated devices and from one dataset, and we say so on every screen where it "
          "matters. The system passes 175 backend and 54 frontend tests. The review paper was submitted to the 9th "
          "International Conference on Pattern Analysis, Understanding and Learning (PAUL 2026), and its camera-ready summary "
          "is in Annexure II."),
    ("h2", "5.2 Future Scope"),
    ("bul", [
        "Make adaptation aware of the label delay from the start, and try a signal that needs no labels, such as disagreement "
        "between a cheap model and a strong one.",
        "Run the testbed on a real Raspberry Pi class device with the kit we built, measure real time and memory, and add "
        "energy measurement.",
        "Repeat the experiments on a second dataset from a different network, such as IoT traffic, and on data from a "
        "different period.",
        "Run the full protocol of 333 trials on a quiet machine, one trial at a time, with all ten seeds.",
        "Recalibrate the cost model for each device tier, and compare with a compiled implementation of the pipeline.",
        "Use cost-sensitive learning or active labelling for the rarest attack types.",
        "Learn the effort levels online instead of fixing them, as the review's question about searching over configurations "
        "suggests.",
    ]),
]

CHAPTERS = [
    (1, "INTRODUCTION", CH1),
    (2, "LITERATURE SURVEY", CH2),
    (3, "SYSTEM DESIGN & ANALYSIS", CH3),
    (4, "RESULTS AND OUTPUTS", CH4),
    (5, "CONCLUSION", CH5),
]
