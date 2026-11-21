# Pre-registration: do curated lessons make Ezra better per token?

**Status: DRAFT.** It counts as registered only once it's committed to the public repo *before* the
first live run of the main experiment. After that, changes go in a dated "Deviations" section at
the end and are never edited in silently.

**Plan it comes from:** `docs/research/progressive-learning.md` §5. **Code:** `src/ezra/experiment.py`,
`src/ezra/learner/`. **Tasks:** `experiments/progressive-learning/tasks/`.

## 1. Question

On coding tasks it has never seen, does Ezra with curated lessons (D-012) succeed more often, and
more cheaply per success, than the same Ezra without lessons? And does it still win against a
control that gets the same extra tokens in another form?

## 2. Hypotheses

- **H1 (primary):** on held-out tasks, the `lessons` arm has a higher hidden-test success rate than
  `control`.
- **H2:** `lessons` has a lower cost per successful held-out task than `control`.
- **H3:** `lessons` beats `budget_matched` on held-out success, which would mean the gain is from
  learning, not just from spending more tokens.
- **H0 to beat** (Hajimiri et al., EMNLP 2026): `budget_matched` does as well as `lessons`.

## 3. Arms

Arms differ by configuration only (`ARMS` in `src/ezra/experiment.py`), never by code path.

| Arm | Learn tasks | Held-out tasks | Difference |
|---|---|---|---|
| `control` | memory `off` | memory `off` | none |
| `lessons` | memory `lessons`: use lessons and learn from each task | memory `frozen`: use lessons, learn nothing | the treatment |
| `budget_matched` | memory `off`, plus 1 extra fix round | same | spends extra tokens on retrying instead of on lessons |

The `naive memory` arm (§5.2 D) is left out of this round.

**Fixed across arms:** model ids and routing (`config/routing.yaml`), prompts, Guardian rules and
rubric, limits, `config/learning.yaml` v`lessons-v1` (cap of about 700 lesson tokens, 3 lessons per
task, retire margin 2), and the fixture project. Every arm and run gets its own fresh database.

## 4. Tasks

- Each task runs on a fresh git copy of `fixture/` (a small package called `minitext`), so tasks
  are independent and only lessons can carry anything from one task to the next.
- Each task folder has three parts:
  - `task.yaml`: what Ezra is told (the description, Acceptance Criteria and constraints).
  - `hidden/`: tests Ezra never sees, copied in only after the run.
  - `reference/`: a known-good solution, used only to check that the task is fair.
- **Fairness gate** (`ezra experiment validate`, also part of the test suite): every task must pass
  all of these:
  - the hidden tests fail on the untouched fixture;
  - the reference solution passes the hidden tests;
  - the reference solution passes the fixture's own tests;
  - the hidden tests never mention a criterion id.
- **Split by category:** the learn and held-out sets share no category, so a lesson can only help
  by transferring a general idea, never by memorizing an answer.
  - Fold 1 (this draft): learn = `new_function`, `bug_fix`, `docs`; held-out = `edge_case`, `refactor`.
  - A second fold swaps them.
- **Target size:** about 60 tasks (40 learn, 20 held out). *This draft has a starter set of 10
  (6 learn, 4 held out). The main run waits until the set is complete.*
- **Order:** learn tasks first, then held-out tasks, each shuffled with the run number as the seed.
  Every arm sees the same order within a run.

## 5. Measures

- **Primary:** whether the hidden tests pass, for each held-out task. Guardian's verdict is *not*
  the primary measure, so Ezra isn't graded by its own judge.
- **Secondary:**
  - cost per successful task, and total tokens (input, output, cache read);
  - Guardian PASS rate, and how often a task needed a REVISE or ended in an ESCALATE;
  - lesson tokens injected per call;
  - negative transfer: tasks `control` solved that `lessons` failed.
- **Per lesson:** uses, helpful and harmful counts.

## 6. Analysis (fixed before any data)

- **Runs:** at least 3 per arm. The unit of analysis is a (run, held-out task) pair.
- **H1 and H3:** the difference in success rate, paired by (run, task). Report a 95% percentile
  bootstrap interval (5,000 resamples, seed 0; `paired_difference`) and an exact McNemar test.
  H1 is supported if the interval's lower bound is above 0.
- **H2:** a Wilcoxon signed-rank test on paired per-task cost, and cost per success with a
  bootstrap interval.
- **Variance:** report the run-to-run spread for every headline number.
- **Rule:** every result is published, including null and negative ones.

## 7. Threats and guards

| Threat | Guard |
|---|---|
| Lessons leak answers | Split by category; the validator rejects ids, test paths and task values; spot-checked by hand |
| Ezra grades itself | Hidden tests are the primary measure |
| "It's just more tokens" | The `budget_matched` arm |
| Nondeterminism | At least 3 runs; spread reported |
| Model changes mid-run | Pinned ids; arms interleaved within each run, all in the same window |
| Small sample | Intervals reported; a second fold; claims limited to this task family |
| Ceiling effect | Pilot first: if `control` already passes over 90% of held-out tasks, add harder tasks before the main run |

## 8. Procedure and budget

1. Complete the task set; `ezra experiment validate` must report every task as fair.
2. **Pilot**, needing your yes. 10 tasks × 3 arms × 1 run = 30 task runs, about $1.50–$3.00. It
   checks the plumbing, the ceiling and real costs. Pilot data is not part of the main result.
3. Commit this file (its status becomes "registered").
4. **Main run**, needing your yes and a cap. 60 tasks × 3 arms × 3 runs = 540 task runs plus about
   120 reflections, roughly $28–$56. Run it with `ezra experiment run --runs 3 --max-usd <cap> --confirm`,
   spread over days if the daily limit requires it.
5. `ezra experiment report`, then a scrubbed results README.

## 9. Open questions for Sam

1. Should the arm order inside a run be randomized as well? Right now it's always control, lessons,
   budget_matched.
2. Is one extra fix round the right budget match, or should the extra tokens go to higher effort?
3. Should the second fold be part of the main run, or a follow-up?

## Deviations

*(none yet)*
