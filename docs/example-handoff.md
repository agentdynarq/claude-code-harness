# Handoff: fix VAT rounding on half cents

This is the handoff template filled in for the example task. Its values were copied from
the `scripts/demo.py` run recorded in
[`evidence/2026-10-11-demo-windows-py313.txt`](evidence/2026-10-11-demo-windows-py313.txt),
where the script, not Claude, applied the fix in a temporary copy. It lives here rather
than next to the brief because `examples/invoice-totals` still contains the bug.

Date: 2026-10-11
Brief: `examples/invoice-totals/docs/tasks/fix-vat-rounding.md`

## Completed work
- `invoice_totals/totals.py`: VAT per rate now rounds with
  `quantize(CENT, rounding=ROUND_HALF_UP)` instead of `round(..., 2)`, which rounded
  half to even. Grouping and summing per rate are unchanged.
- No test changes: the 5 existing tests already cover acceptance criteria 1 to 5.

## Evidence
- Command: `python .claude/harness/verify.py`
- Result: PASSED. `tests` (required) PASSED, exit 0. `typecheck` (optional) SKIPPED:
  mypy is not a dependency of the example.
- Source state: `74eb229d6ac5` (before the fix: `2e1c003125f9`)
- Evidence status at handoff: FRESH (`verify.py status`, exit 0)
- Report: `.claude/harness/evidence/latest.json`

## Unresolved problems
- `typecheck` never ran, so type errors are unverified.
- Rounding is tested only for positive amounts. Credit notes with negative amounts are
  not covered by any test.

## Next action
- Project owner: decide whether credit notes are in scope and, if so, add a brief for them.
