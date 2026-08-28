# Human acceptance record — 2026-08-02 (warm-subject edition)

- **Subject**: the project owner. **Contamination statement**: the subject had read all the build
  reports and is not the "uninvolved reviewer" in GOAL.md's sense; this record is the warm edition;
  a re-test on a naïve subject with `docs/TESTING_FACILITATOR.md` should follow.
- **Contamination handling**: anchors that had appeared in the reports (00134dd3 amount_due, 0079863f,
  rejection count 623) were all abandoned, replaced with new anchors of the same type from the artifacts.
- **Facilitator**: Claude (running per `docs/TESTING_FACILITATOR.md`).
- **Materials**: `runs/demo/` (generated 2026-08-02, byte-for-byte identical to the latest code).

## Anchors (this edition)

- T1: doc `002e3cf97973428f905671b3`, invoice_number, value `t 096084`
- T2: recompute "428 blocking findings" (1098 total findings)
- T3: example doc `00136a27` due_date (dws_returned_no_value)
- T4: doc `0096d69f865b443290705bee` (net=due=$2,737.00, gross=$3,220.00)
- T5: panel phrasing judgment

## Per-task record

**T1 round one (failure, presentation defect)**: facing `00134dd3/amount_due` (unsupported; the value
21,900.66 rejected at freeze) the subject could not answer, verbatim: "no source image — a human can't
understand it". **Verdict: not the subject's fault, a presentation failure** — rejected rows carried no
admitted claim, and the panel rendered evidence only by "which span the value falls in", so the rows most
in need of human adjudication were precisely the ones without an image. The span DWS pointed to (ES-0003,
regional OCR 21,000.00) had existed all along; it simply was never shown to the reviewer.
**Handling**: matrix rows gained `cited_span_ids` (grouped by field, regardless of whether the value falls
inside); the panel renders rejected rows with the "DWS points here (for review)" crop + independent OCR +
label; rows with no cited region (typically missing values) get a full-page render link; full-page renders
entered the pipeline and the audit bundle. 3 tests (rejected rows have images / no-citation rows get a
full page / cited does not follow the claim). The demo was regenerated.

**T1 round two (after the fix, pass)**: comparing the ES-0003 crop with the independent OCR, the subject
judged unaided: "the actual price is 21,000; DWS's 21,900.66 is wrong; the system was right to reject";
and stated the mechanism (binding coverage 0.3333 < 0.8). Reason + mechanism + evidence location, all
three present.

**Incidental output (beyond scope)**: while browsing, the subject unprompted found two transcription
errors in the DWS value of `00134dd3/buyer_name` (GREENSBORG missing an O; zip 67405 should be 27405),
with the paper, the independent OCR, and the crop all in agreement. Recorded as a formal adjudication via
`python3 -m invoiceloop adjudicate` (adjudication_ledger seq 1, decision=correct) — M4's first use by a
real human; the "machine rejects wrong + human corrects" loop walked end to end.

**T2 part one (pass)**: the subject recomputed 428 with
`grep -c '"blocking": true' runs/demo/gate_report.json`, matching the authoritative count.
Facilitator-kit wording fix: "count them yourself" reads easily as counting line by line by hand;
changed to "recompute from gate_report.json with a one-line command" (subject, verbatim: "don't make a
human count 428 lines — that's impossible").

| Task | Right/Wrong | Artifact found? | Elapsed | Subject's verbatim words (key sentence) |
|---|---|---|---|---|
| T1 | Round one: presentation failure (fixed); round two: **right** | panel row + ES-0003 | ~6min | "the price here is actually 21000" / "no source image — a human can't understand it" |
| T2 | **right** (both parts) | gate_report.json / field_ledger.json | ~4min | "grep -c '\"blocking\": true'" / "this is the hash of the whole ledger; change one character and it changes" |
| T3 | **right** | panel row + GF-0048 + full page p2 | ~4min | "shouldn't the buyer name be harry huge" / "the big model didn't read it out of the image?" |
| T4 | **right** | the disputed row's limitation text | ~4min | "shouldn't go into errors, right" / "put it into the caliber-conflict bucket, not error detection" |
| T5 | **right** | panel thesis block | ~1min | "doesn't prove trustworthiness, only that 'the system extracted such-and-such information'" |

**T3 (pass)**: the subject found the missing-value row `003cc916/buyer_name` (blocking finding GF-0048,
repair route vision_reread), and following the route opened full page p2 and found
`For Harry Huge, Esq.` — the "block → route → human reads the image and adds the value" chain walked
bare-handed; recorded as adjudication seq 2. Second class: stated that `visual_not_measured` means
"not yet measured" rather than "no problem", with the three-way meaning of dash vs "pass" vs "reject"
stated accurately.

**T4 (pass)**: doc `0096d69f`. The subject gave the correct conclusion first (not into the error rate),
and after two rounds of follow-up stated the full mechanism: paper Gross = list price (client side),
Net = the agency's actual pay after the 15% commission; due = net = $2,737.00 → the page places the amount
payable on the Net side → the two vocabularies point in opposite directions; "gross was extracted wrong"
is a misdiagnosis. Final answer: "goes into the caliber dispute (human adjudication), not into the error
rate".

**T5 (pass, veto line avoided)**: the subject answered "doesn't prove trustworthiness, only that the
system extracted such-and-such information"; after calibration, accepted the deliverable as "mechanically
verifiable support relations", and pointed to where the phrasing lives: the panel front-page thesis block
("extraction correctness cannot be trusted, support relations are verifiable … it does not say this value
is right").

## Verdict

**Pass (warm-subject edition)**: T1–T4 all correct (line ≥3) and T5 answered correctly.
One real presentation defect found (T1 round one: rejected rows had no review evidence), fixed, and the
demo regenerated; two facilitator-kit wordings revised. Outstanding: a naïve-subject re-test with
`docs/TESTING_FACILITATOR.md` (this edition's subject had read the build reports; contamination scope
stated in the file header).

**Incidental output**: two real-human adjudications entered `runs/demo/adjudication_ledger.jsonl`
(seq 1 zip correction, seq 2 buyer-name value add) — M4's first full-pipeline run.
