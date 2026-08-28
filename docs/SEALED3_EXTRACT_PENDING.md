# SEALED-3 extraction status (completed 2026-08-07 · sealed, unread)

List: `docs/sealed3_doc_list.json` (drand round 6356175, context=`sealed3-v1`).
Protocol: `docs/SEALED3_PROTOCOL.md`.

**Discipline:** record the ops summary only; `must not` `run` / unseal-evaluate / read raw /
tune vocabularies or strategies on this batch. Unsealing requires a separate adjudication and a written `SEALED3_RESULTS.md`.

**Completed (ops only):**

1. Dual-mode extraction → `runs/sealed3-workspace/raw/`
   - `done=200` `skipped=0` `failed=0`
   - `spent_estimate≈4992` credits · `keys_used=1`
   - Verified: 200 documents with `http_status=200`, missing/non-200 = 0
2. Did **not** run the primary-arm `run`, did not write RESULTS, did not attach any qualification marker.

This batch is now sealed as the current sole unseen candidate set; before unsealing, it must not be claimed that the final held-out has passed.
