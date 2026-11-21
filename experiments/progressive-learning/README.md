# Progressive learning experiment

Does Ezra learn from experience in a way that pays for itself? See `PREREGISTRATION.md` for the
design, and `docs/research/progressive-learning.md` §5 for the reasoning behind it.

| Path | What |
|---|---|
| `fixture/` | `minitext`, the small project every task starts from (a fresh git copy each time) |
| `tasks/<id>/task.yaml` | What Ezra is told: description, Acceptance Criteria, constraints; plus split, category and section (not shown to Ezra) |
| `tasks/<id>/hidden/` | Tests Ezra never sees; they decide true success |
| `tasks/<id>/reference/` | A known-good solution, used only to prove the task is fair |

```
ezra experiment validate                 # every task fair? (no model calls)
ezra experiment estimate --runs 3        # what a run would cost (no model calls)
ezra experiment run --arms control,lessons --runs 1 --max-usd 3 --confirm   # live: spends money
ezra experiment run --sections review --arms control --runs 1 --max-usd 1 --confirm   # one section
ezra experiment run --difficulty hard --label pilot-2 --arms control --runs 1 --max-usd 3 --confirm
ezra experiment report                   # success, cost per success, paired difference with 95% CI, per section
ezra experiment report --label pilot-2   # the results of one labelled run
```

`--difficulty easy|hard` works on every subcommand and picks one task set. `--label NAME` (on `run`
and `report`) keeps a run's results in their own folder, so a new pilot never collides with an old one.

Results go to `.ezra/experiments/progressive-learning/` (or a `<label>/` folder inside it; gitignored): one database per arm and run,
plus `results.jsonl`. Scrub them before publishing anything.

## Adding a task

1. Make `tasks/<id>/` with a `task.yaml` like the others. Use the `learn` or `heldout` split
   according to the category rule in the pre-registration, and a `section`
   (`plan`, `build`, `test` or `review`) for the stage the task stresses, and a `difficulty`
   (`easy` or `hard`; hard means the obvious change trips an existing test or a stated rule).
2. Write the hidden tests to go a little beyond the criteria, the way a careful user would check
   the work, without testing anything the criteria don't imply. Never put a criterion id in them.
3. Put the full changed files of a correct solution under `reference/`, at the same paths as in
   the fixture.
4. Run `ezra experiment validate`.
