# claude-code-harness

Starter kit for using Claude Code on existing projects: templates, one skill, a check
runner and an optional Stop hook. This file is for working on the kit itself.

## Architecture constraints
- Standard library only, Python 3.11 or newer. No PyPI dependencies, no network calls.
- `kit/` is exactly what `install.py` copies into a user's project. Anything added there
  ships to users. Never add a settings file or a file named `CLAUDE.md` under `kit/`.
- `stop_hook.py` must never exit with code 2 and must never block on missing or invalid
  configuration.
- `install.py` only creates files. It must not overwrite, merge into settings, or run
  project commands.
- `examples/invoice-totals` contains a deliberate bug. Do not fix it in place; the demo
  and the tests depend on it.

## Commands
- Tests: `python -m unittest discover -s tests`
- Walkthrough: `python scripts/demo.py`
- Deliberate defects (slow, about 2 minutes): `python scripts/mutation_check.py`

## Handle with care
- `kit/.claude/harness/stop_hook.py` and `verify.py`: behaviour is documented in the
  README and pinned by tests; update both together.
- `docs/claude-code-contract.md`: update it when a Claude Code fact the kit relies on changes.

## Definition of done
- All tests pass and `scripts/demo.py` reports every expectation met.
- A new check or rule comes with a test, and `scripts/mutation_check.py` has a defect
  that the test catches.
- No em dashes or en dashes anywhere (a test enforces this).
- Evidence claims in `README.md` and `docs/evidence/` match a recorded run.

## Where details live
- Claude Code behaviour relied on: `docs/claude-code-contract.md`
- What was tested, where and how: `docs/evidence/README.md`
- Decisions: `PLAN.md`
