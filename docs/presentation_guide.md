# Presentation guide

How to walk a panel through the project in the app, what to say on each screen, and the questions
to expect. The app's navigation is numbered 1–6 in the same order as this guide, and every page ends
with a "Next" button, so you never have to think about where to go.

Total time: about 10 minutes, plus questions. Numbers quoted here are from the saved reports as of
12 November 2026; the **Findings** page always shows the current ones, so read numbers from the
screen, not from memory.

## Before you start

1. Start the backend and the frontend (two terminals):

   ```bash
   cd ~/Documents/Adaptive_ML_Studio/backend && PYTHONHASHSEED=0 .venv/bin/uvicorn adaptiveml.api.app:app --port 8000
   ```

   ```bash
   cd ~/Documents/Adaptive_ML_Studio/frontend && npm run dev
   ```

2. Open <http://localhost:5173> and reload the page once. The top bar should say **Connected**.
3. Close other heavy programs. Runs are timed, and a busy laptop makes the timings worse.
4. On any page after Home, switch on **Presentation mode** (top bar) for larger text.
5. Do one practice run of the Testbed demo (Step 4) so you know it takes about 40 seconds.
6. If the network or the projector fails, the **Findings** page and the saved reports need no run
   at all: you can present from Step 5 alone.

## One-sentence summary (memorise this)

> Our published review proposed a system that adapts to changing data and to a device's limited
> resources at the same time, but did not test it. We built it, tested it on a week of real network
> traffic with real cyber-attacks, found where it fails, and designed a controller that does better
> within the device's budget.

---

## Step 1 · Home — the problem (about 1.5 minutes)

**Show:** the Home page. Scroll slowly: the curve at the top, "The problem", then "From a review
paper to a tested system", then "The project in six steps".

**Say:**

- "This is AdaptiveML Studio. It is the tool we built to study one problem: a machine-learning model
  is trained on past data, but the world keeps changing. When the data changes, the model keeps
  applying an old rule, and its accuracy drops without any warning. This is called concept drift."
- (At the curve) "The dashed line is a model trained once. The solid line is a model that adapts.
  This picture is only an illustration; the real measurements come next."
- (At "From a review paper to a tested system") "Our review paper surveyed twenty studies. We found
  that the pieces exist separately, and that most are judged only on accuracy. The review proposed
  five decision rules for adapting to changing data and to limited device resources together, and
  it said clearly that they were not tested. This project tests them."
- (At the six steps) "The app follows the order of our work. I will go through it step by step."

**Click:** *Next: Live demo* at the bottom.

## Step 2 · Live demo — see it happen (about 2 minutes)

**Show:** the Live demo page. Keep the first dataset (Electricity) and the *sudden* change, and
start the replay.

**Say:**

- "Here are two models on the same real data, row by row. One learned once and stopped. The other
  keeps learning and watches its own errors."
- "At a row we choose, we change the data on purpose, so we know exactly where the change is. Watch
  the two accuracy lines."
- (When the lines separate) "The frozen model falls and stays down. The adaptive one falls, the
  detector raises an alarm, a replacement model is trained, and accuracy comes back."
- "Every prediction is made before the model sees the true answer for that row. That is the fair
  way to test a model on a stream."

**If asked why the change is artificial here:** "On this small dataset nobody has marked where the
real changes are, so we add one at a known place. In Step 4 we use a dataset where the changes are
real and dated."

**Click:** *Next: Experiments*.

## Step 3 · Experiments — compare methods (about 1 minute)

**Show:** the Experiments page, then the list of recorded runs. Open one run briefly.

**Say:**

- "Watching one run is not evidence. Here each method runs alone in its own process on the same
  data, so their timings do not disturb each other."
- "Every run is saved with its settings, its random seed and the machine it ran on, and it can be
  re-run to check that it gives the same predictions."
- "We always record two things together: how good the predictions are, and what they cost in time
  and memory. Most earlier studies report only the first."

**Click:** *Next: Testbed*.

## Step 4 · Testbed — a real case (about 2.5 minutes)

**Show:** the Testbed page. Click **Use demo settings**, then **Run testbed experiment**. While it
runs (about 40 seconds), talk. When it finishes, click **View results**.

**Say while it runs:**

- "This is the real case. The data is CIC-IDS2017 in its corrected version: 2.1 million real network
  connections recorded over one working week, with different cyber-attacks on different days. The
  task is to decide, for each connection, attack or normal."
- "We imagine this running on a small device such as a router, which has little time per connection
  and little memory. We do not have such a device, so we enforce the limits in software. The screen
  says *simulated* and *placeholder budgets* everywhere, because that is what they are."
- "The demo compares three things on 40,000 connections that contain two real attacks: simply
  copying the previous answer, the five rules from our review, and our new controller."

**Say on the results:**

- "Look at accuracy first: even copying the previous answer scores above 90 percent, because attacks
  come in long runs. So accuracy alone is misleading here."
- "This column, κ-temporal, is the gain over copying. Zero means no better than copying; one is
  perfect. That is the score we use."
- "Below, the time per connection is split by pipeline stage, and for the controllers you can see
  which rule fired and how often."

**Do not** promise specific numbers for the live run: it is one short run, and timings change with
the laptop's load. The recorded results are on the next page.

**Click:** *Next: Findings*.

## Step 5 · Findings — what we found (about 2.5 minutes)

**Show:** the Findings page. One finding per scroll.

**Say:**

- **Finding 1.** "On the whole week, copying the previous answer is right 98.7 percent of the time.
  All learning methods look the same on accuracy. On gain over copying they separate clearly, and
  the most accurate methods cost many times more per connection."
- **Finding 2.** "Our review said it was an open question which stage of the pipeline costs the
  most. We measured it: preparing the data and updating the model take about three quarters of the
  time. Checking for drift is cheap."
- **Finding 3.** "The five rules from the review keep quality, but on the small device they overshoot
  the time budget by about 60 percent. Our new controller does less work on easy connections and more
  during attacks, and stays at or near the budget. On Wednesday, the day we designed it on, it made
  27 percent fewer errors on the small device. On Thursday and Friday, which we did not use in the
  design, it made equal or fewer errors on both devices, in about half the time. So the claim that
  holds is: equal or fewer errors, at the budget."
- **Finding 4.** "We also report what does not work. In real life the true answer arrives late. When
  it arrives 1,000 connections late, both controllers do badly and simple continuous learning does
  much better. This is our main open problem."
- **Held-out days.** "We designed the controller using Wednesday. To check we had not just fitted
  that day, we ran it unchanged on Thursday and Friday. It still stays at or near the budget, at
  about half the rules' cost on the small device, with equal or fewer errors. And unlike the rules,
  it gives the same result every time we run it."
- **Limits.** "The devices are simulated and it is one dataset from one network. We say this on the
  page."

**Click:** *Next: Method*.

## Step 6 · Method — how it works (about 30 seconds, or use for questions)

**Say:** "This page documents every component, how each number is measured, and which gap from the
review it addresses. I will use it if you have questions on the details."

**Close with:** "To summarise: we turned an untested proposal from our review into a working system,
measured it on a real case, showed where it fails, and proposed a controller that does better within
the budget on a small device, with its limits stated openly."

---

## Questions the judges may ask

### About the idea

**What is concept drift, in one line?**
The relationship between the inputs and the correct answer changes over time, so a model trained on
old data becomes wrong.

**What is new in your work?**
Three things. (1) The first test of our review's five decision rules, on a real stream, including
where they fail. (2) A stage-by-stage cost measurement that answers a question our review left
open. (3) A new controller that spends the device's time budget where it matters. We did not invent
a new learning algorithm.

**Is the new controller really new?**
We checked the literature. The closest work we found (RCCDA, 2025) decides whether to update a model
under an average budget. Ours controls every pipeline stage, handles drift, and respects hard time
and memory limits on a real intrusion stream. We found no work that combines these, but we say
"to our knowledge": our confidence is medium, not certain.

**How does the new controller work, simply?**
It keeps a "price" for computing time. If the device is spending more than its budget, the price
goes up; if less, it goes down. For each connection it picks the amount of work that is worth that
price: little work on easy stretches, full work when the stream is changing or an attack is starting.

**Why not just use the most accurate model?**
The most accurate methods (Adaptive Random Forest, Streaming Random Patches) cost about 5 to 45
times more time per connection. On a small device that is not affordable. Our question is what is
the best you can do inside a budget.

### About the data and the evaluation

**Why this dataset?**
It is real traffic with real attacks at known times, so the changes in the data are not invented by
us. We use the corrected version published by researchers who fixed labelling errors in the
original. It is also relevant to cyber-security, where our review was submitted.

**Why not use accuracy?**
Because attacks arrive in long runs, repeating the previous answer scores 98.7 percent. A method can
look excellent without learning anything. κ-temporal measures the gain over that copycat.

**What is κ-temporal exactly?**
(accuracy of the method − accuracy of copying the previous label) ÷ (1 − accuracy of copying). It is
an established measure for streams (Žliobaitė and colleagues, 2015); we did not invent it.

**Is the drift real or injected?**
In the Live demo (Step 2) it is injected, and labelled as such. In the Testbed (Step 4) it is real:
the attack periods come from the dataset's own schedule.

**How do you know your numbers are reliable?**
Each method runs alone in a fresh process; settings and seeds are saved; confidence intervals come
from resampling blocks of the stream; and the new controller makes its decisions from a cost model,
so the same settings give identical predictions. The weak point is that the controller results are
from one run on one day, which we state.

### About the limits (answer these plainly)

**Did you test on a real edge device?**
No. The limits are enforced in software on a laptop, with placeholder budget values. It shows how
the controllers behave under limits; it does not show performance on a specific device. The kit to
repeat the runs on a Raspberry Pi is built and rehearsed (Testbed → Real device), but we have not run
it on a device yet. Energy is not measured.

**Your controller fails with delayed labels. Is that not a serious problem?**
Yes, and we report it. With answers arriving 1,000 connections late, both controllers reset their
models at the wrong moments, and plain incremental learning does better. We found the cause (the
resets), but our first fix did not work. It is our main open problem.

**Is one dataset enough?**
No, for a general claim. Our results are for this one week of traffic from one lab network. A second
dataset is the next step.

**Did you tune on the test data?**
The controller was designed using Wednesday's traffic, so the Wednesday result is not a clean test,
and we say so. We then tested it, without changing anything, on Thursday and Friday, which were not
used in the design. There it stays at or near the time budget on both device sizes, where the
review's rules run 42 to 53 percent over on the small device. Its errors are equal to the rules' on
the small device and equal or fewer on the smallest one. So the cost result held; the "fewer errors"
result from Wednesday held only partly. Details: `research_testbed/research/heldout_results.md`.

**Your method is still far less accurate than Adaptive Random Forest. Why does it matter?**
Because it costs about one thirteenth of the time. The comparison that matters on a small device is
between methods that fit the budget.

**What about rare attacks?**
Five attack types have fewer than 110 connections in the whole week. Two of them (Heartbleed with 11
connections and SQL injection with 13) are missed by every method, including the expensive ones, and
the other three are caught poorly and unevenly. We report this per attack type and do not average
them into a flattering number.

### About the work itself

**What did each team member do?**
Three workstreams: review and literature; implementation (this platform); research and
experimentation. (Give the names and your own part.)

**Which tools did you use?**
Python with River for stream learning (Hoeffding trees, ADWIN drift detection), FastAPI for the
server, React and TypeScript for the interface. Everything is open source.

**How is this connected to your review paper?**
Directly. The five rules (R1–R5), the cost formula and the open questions are taken from the review.
The project tests the rules, measures the cost formula term by term, and proposes an answer to the
open question about choosing the pipeline's configuration.

**What would you do with three more months?**
(1) Test on days and datasets not used in the design, with repeated seeds. (2) Solve adaptation under
delayed labels. (3) Run on a real Raspberry Pi and measure energy.

---

## What not to claim

- Not "a new machine-learning algorithm". Say "a new controller for standard stream learners".
- Not "tested on edge devices". Say "simulated device limits".
- Not "our method is the most accurate", and not "it always makes fewer errors than the rules". Say
  "equal or fewer errors than the review's rules, at or near the budget, which the rules exceed".
- Not "it works in real deployments". The delayed-label result shows it does not yet.
- No energy numbers. None were measured.
