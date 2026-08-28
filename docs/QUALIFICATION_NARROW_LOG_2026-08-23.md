# QUALIFICATION_NARROW_2026-08-22 Run Log

Protocol body: `docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md`, frozen at `b45f983`.
The file has since been restored to a byte-for-byte copy of that commit, but it was indeed modified at `1afe7da` during extraction; that historical
fact triggers §7 and cannot be offset by "the final bytes are identical." This document is a run record kept outside the protocol.

## 1. Construction note: budget parameter too low, extraction completed in two segments

This is a construction note, not an experimental event: the first segment tripped the circuit breaker by design at the 222nd call with the default `--budget 6000`, having accumulated
6006 credits (0 failures); the second segment resumed from checkpoint with `--budget 15000` and completed the
remaining 178 calls.
Both segments used the same frozen list and schema; every existing `(doc, mode)` was skipped; all 400 responses with status 200 are complete,
the metric inputs are unchanged, and the root cause is simply that roughly 10,800 credits were not reserved for 400 calls at about 27 credits per call.

## 2. One protocol-body modification that had to be declared (reverted)

On 2026-08-23, mid-extraction, I wrote the content of section 1 above **directly into protocol body §3** and committed it
(`1afe7da`). Protocol §7's dirty-arm clause names any change to "the body of this protocol" = dirty arm.

Handling: immediately restored with `git checkout b45f983 --`; the protocol file is **byte-for-byte identical** to the frozen commit
(`git diff b45f983 -- docs/QUALIFICATION_NARROW_PROTOCOL_2026-08-22.md` is empty),
and the record was moved to this document.

**Why it is still reported rather than treated as if it never happened**: that change really did only add a run note, touching neither the sampling salt,
the list, the arm policies, the metric definitions, nor any prediction — it could not have affected the results. But "this change was harmless, so it does not count" is exactly
the style of reasoning the dirty-arm clause exists to block — the clause is written broadly precisely so that no one gets to judge after the fact which changes were harmless.
So: declare, revert, and leave the judgment to the reader.

No arm was run during the modification window (the four arms began only after extraction completed); `1afe7da` and its revert are both
traceable in git history.

## 3. Timeline

| Time (local) | Event |
|---|---|
| 2026-08-22 | Protocol and the 200-document list frozen (`b45f983`); `raw/` empty |
| 2026-08-23 | Extraction segment one: 222/400, 0 failures, budget circuit breaker |
| 2026-08-23 | Protocol body modified (`1afe7da`) → reverted the same day, record moved into this document |
| 2026-08-23 | Extraction segment two: completed 400/400 |

## 4. Subsequent status ruling

Restoring the frozen bytes does not undo the contamination protocol §7 already triggered. A subsequent audit on that basis formally ruled this round's status
`contaminated / blocking`, revoking the qualification / product-capability promotion; the original numbers are retained as
exploratory measurements. See `docs/QUALIFICATION_NARROW_CONTAMINATION_2026-08-23.md`.
