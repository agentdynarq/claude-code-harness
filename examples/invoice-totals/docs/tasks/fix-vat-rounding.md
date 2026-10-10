# Task: fix VAT rounding on half cents

## Objective
VAT for each rate must round half a cent away from zero, as `CLAUDE.md` requires.
`invoice_totals()` currently uses Python's `round()`, which rounds half to even on
`Decimal`, so 1.50 net at 19% gives 0.28 VAT instead of 0.29.

## Scope
- `invoice_totals/totals.py`: the VAT rounding step.
- `tests/test_totals.py`: new cases only if a criterion below is not already covered.

## Exclusions
- No change to how net amounts are grouped and summed per rate.
- No `float` arithmetic, no new dependencies.
- No change to `.claude/harness/` or `CLAUDE.md`.

## Acceptance criteria
1. 1.50 net at 19% gives VAT 0.29 and gross 1.79.
2. 3.50 at 7% plus 1.50 at 19% gives VAT 0.54 and gross 5.54.
3. 2 x 10.00 at 19% still gives VAT 3.80 and gross 23.80.
4. 3 lines of 0.04 at 19% still give VAT 0.02 (summed per rate before rounding).
5. A quantity of 0 or below still raises `ValueError`.
6. `python .claude/harness/verify.py` reports PASSED and `status` reports FRESH evidence.

## Verification commands
```
python -m unittest discover -s tests -v
python .claude/harness/verify.py
python .claude/harness/verify.py status
```
