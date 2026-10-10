# Live Claude Code session record: regression, 2026-10-11

Written by scripts/live_session_check.py. Paths are replaced with <project>, ~ and <user>.

- Claude Code: 2.1.296 (Claude Code)
- Model: claude-opus-5-5
- Prompt: `In invoice_totals/totals.py, change the VAT rounding mode from ROUND_HALF_UP to ROUND_HALF_EVEN. Make only that edit. Do not run tests or any other command.`
- Exit code: 0
- Result: `{"subtype": "success", "is_error": false, "num_turns": 5, "duration_ms": 22006, "total_cost_usd": 0.1333702}`
- Permission denials: 0

## Tool calls
- `Read: <project>\invoice_totals\totals.py`
- `Edit: <project>\invoice_totals\totals.py`
- `Edit: <project>\invoice_totals\totals.py`

## Text that reached Claude as a user turn (the prompt and any hook feedback)
```
Stop hook feedback:
claude-code-harness: required checks did not pass, so this turn was not allowed to end (automatic retry 1 of 2).
Source state a7eb98ebdbd8. Full report: .claude/harness/evidence/latest.json

tests: FAILED, exit code 1
  | test_vat_is_rounded_per_rate (test_totals.InvoiceTotalsTest.test_vat_is_rounded_per_rate) ... FAIL
  | test_whole_cent_vat (test_totals.InvoiceTotalsTest.test_whole_cent_vat) ... ok
  | 
  | ======================================================================
  | FAIL: test_half_cent_vat_rounds_away_from_zero (test_totals.InvoiceTotalsTest.test_half_cent_vat_rounds_away_from_zero)
  | ----------------------------------------------------------------------
  | Traceback (most recent call last):
  |   File "<project>\tests\test_totals.py", line 23, in test_half_cent_vat_rounds_away_from_zero
  |     self.assertEqual(totals.vat, Decimal("0.29"))
  |     ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  | AssertionError: Decimal('0.28') != Decimal('0.29')
  | 
  | ======================================================================
  | FAIL: test_vat_is_rounded_per_rate (test_totals.InvoiceTotalsTest.test_vat_is_rounded_per_rate)
  | ----------------------------------------------------------------------
  | Traceback (most recent call last):
  |   File "<project>\tests\test_totals.py", line 29, in test_vat_is_rounded_per_rate
```

## Stop hook runs in the debug log
    2026-10-10T19:06:54.449Z [DEBUG] Hooks: Stop [python ${CLAUDE_PROJECT_DIR}/.claude/harness/stop_hook.py] finished with status 0 (616ms)
    2026-10-10T19:07:01.571Z [DEBUG] Hooks: Stop [python ${CLAUDE_PROJECT_DIR}/.claude/harness/stop_hook.py] finished with status 0 (404ms)

## Stop hook state at the end
```
{
  "session_id": "442d784c-8f92-4be1-a6e6-7426941d1f63",
  "consecutive_blocks": 1,
  "notified_fingerprint": "a7eb98ebdbd88204ff53bcb5dcc0e436f1dd30f09bba19cb8df47036e5607d27"
}

```

## verify.py status after the session
```
{
  "state": "fresh",
  "current_fingerprint": "a7eb98ebdbd88204ff53bcb5dcc0e436f1dd30f09bba19cb8df47036e5607d27",
  "report": ".claude/harness/evidence/latest.json",
  "overall": "failed",
  "recorded_at": "2026-10-10T19:06:54Z",
  "recorded_fingerprint": "a7eb98ebdbd88204ff53bcb5dcc0e436f1dd30f09bba19cb8df47036e5607d27",
  "config_changed": false,
  "changes": {
    "added": [],
    "removed": [],
    "modified": []
  }
}

```

## Changes
```
 M invoice_totals/totals.py
?? .claude/harness/README.md
?? .claude/harness/checks.example.toml
?? .claude/harness/hook-settings.example.json
?? .claude/harness/install-manifest.json
?? .claude/harness/stop_hook.py
?? .claude/harness/templates/
?? .claude/harness/verify.py
?? .claude/skills/
?? invoice_totals/__pycache__/
?? tests/__pycache__/

 invoice_totals/totals.py | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)

diff --git a/invoice_totals/totals.py b/invoice_totals/totals.py
index 5a526c8..1914552 100644
--- a/invoice_totals/totals.py
+++ b/invoice_totals/totals.py
@@ -6,7 +6,7 @@ Synthetic example code for claude-code-harness. Not a billing system.
 from __future__ import annotations
 
 from dataclasses import dataclass
-from decimal import ROUND_HALF_UP, Decimal
+from decimal import ROUND_HALF_EVEN, Decimal
 
 CENT = Decimal("0.01")
 
@@ -36,7 +36,7 @@ def invoice_totals(lines: list[Line]) -> Totals:
 
     net = sum(net_by_rate.values(), Decimal("0"))
     vat = sum(
-        ((amount * rate).quantize(CENT, rounding=ROUND_HALF_UP) for rate, amount in net_by_rate.items()),
+        ((amount * rate).quantize(CENT, rounding=ROUND_HALF_EVEN) for rate, amount in net_by_rate.items()),
         Decimal("0"),
     )
     return Totals(net=net.quantize(CENT), vat=vat.quantize(CENT), gross=(net + vat).quantize(CENT))

```

## Final message
I've stopped here without making further changes. The harness's stop hook ran the `tests` check after my edit and 2 of 5 tests failed:

- `test_half_cent_vat_rounds_away_from_zero` (`tests/test_totals.py:23`): expected VAT 0.29, got 0.28.
- `test_vat_is_rounded_per_rate` (`tests/test_totals.py:29`): expected VAT 0.54, got 0.52.

The edit you asked for causes both failures. The tests check the half-up rounding that `CLAUDE.md` requires, and half-even rounds those half-cent amounts down instead. There are 2 ways to make the checks pass, and both need you to decide:

1. **Undo the change:** run `git checkout invoice_totals/totals.py` to go back to `ROUND_HALF_UP`. Doing that myself would go against your request.
2. **Adopt half-even on purpose:** update the 2 tests, the rounding rule in `CLAUDE.md`, and the decision log in `PLAN.md`. That goes beyond the single edit you asked for, and the hook treats changing tests just to pass as weakening them, so it needs your clear go-ahead.

Which would you like?
