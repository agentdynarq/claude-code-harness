# invoice-totals

Synthetic example project shipped with claude-code-harness. It is not a billing system,
and its amounts and rates are test values.

## Purpose
Compute net, VAT and gross totals for an invoice from its lines. Used to demonstrate a
verified change with a real failing test.

## Architecture constraints
- Money is `decimal.Decimal`, never `float`.
- Net amounts are summed per VAT rate first. VAT is computed per rate on that sum and
  rounded to the cent, half away from zero (`ROUND_HALF_UP`), never half to even.
- Standard library only. Python 3.11 or newer.

## Commands
- Test: `python -m unittest discover -s tests -v`
- All required checks: `python .claude/harness/verify.py`

## Handle with care
- `invoice_totals/totals.py`: any rounding change alters every invoice total.

## Definition of done
- The task brief's acceptance criteria are met.
- `python .claude/harness/verify.py` reports PASSED.
- `python .claude/harness/verify.py status` reports FRESH evidence for the final source.
- The diff touches only files in the brief's scope.
- A handoff note sits next to the brief.

## Where details live
- Task briefs and handoff notes: `docs/tasks/`
