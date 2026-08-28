# The Coder's Goal

`ARCHITECTURE.md` says what to build; `CLAUDE.md` says how to work. This file says **what
you optimise when those two are not enough**.

---

## In One Sentence

**Let the person looking at it answer, for every number, "how much should I trust this, and
on what basis" — and make that judgment recomputable.**

Not making extraction accurate — the six rounds of experiments proved that no single signal
can reliably flag all important extraction errors; the "push accuracy up" road is sealed
shut. It is about making the inaccuracy itself **visible, locatable, and gradable**, rather
than hiding it behind an average accuracy number.

---

## What Done Looks Like (falsifiable)

Run one never-before-seen invoice through the full pipeline; a reviewer who does not know
the internals should be able to:

1. Explain, for **any** field, why it is marked at its current tier, without asking anyone
2. **Recompute with zero API calls** every number on the panel from the saved evidence
3. See for which fields the system **explicitly says it does not know** — rather than
   guessing a value and sneaking it through
4. Read on the panel that "extraction itself cannot be trusted", and understand that this
   is not a contradiction — it is the very reason this thing exists

Item 4 is the easiest to sand off during the endgame. Hold that line.

---

## Priorities When They Conflict (highest to lowest)

**1. Honesty > looking good.**
Claims must be backed by artifacts. A weaker but defensible statement always beats a louder
one that needs "roughly" or "basically works" as hedges. A demo does not die from one fewer
highlight; one unprovable sentence forfeits the credibility of all six rounds of
experiments.

**2. Recomputable > complete.**
Any number on the panel that cannot be recomputed from the saved evidence in
`~/Developer/dws-derisk/` does not go on. Better to show three fewer metrics than to add
one of unknown provenance.

**3. Read the implementation > read the handoff.**
Including what I write. I have already given two wrong instructions (`score.normalise`
cannot do token matching; `citation_holds` is substring containment); both times you pushed
back by reading the code — and both times you were right. Keep doing that. Handoff notes
are leads, not facts.

**4. Blocking > silent.**
A check that cannot run, missing evidence, a row that will not bind — record it explicitly
and block; never crush it into a "pass" or a `False`. The `OcrUnavailable` you added
yourself is the correct shape of this rule. A hidden gap is more dangerous than the gap
itself.

**5. Fewer mechanisms > covering every case.**
`ARCHITECTURE.md` §10 lists what is explicitly not done (optimistic concurrency, UoW,
fingerprint replay, supersession...). Those were designed for concurrent multi-agent
long-horizon runs; this domain has no use for them, and copying them over is cargo cult.
**Before adding any new layer of abstraction, first ask which concrete, already-occurred
failure it stops.** If you cannot name one, do not build it — the freeze transaction got in
because it stopped the real mis-binding incident in Round Six.

### §5a Sprint-Period Mechanism Budget (from 2026-08-23, until both submissions are complete)

Until the following three things exist simultaneously, add no new meta mechanisms
(protocol/evidence/audit/freeze/provenance classes):

1. One 2–4 minute recording
2. The README's "For judges" three-command quickstart, verified passing on a clean clone
3. Draft copies of the two submission forms

There is exactly one exception: an already-occurred failure that blocks one of the three
above. Write the failure down, then build the mechanism.

Criterion: new `scripts/qual_*.py`, `invoiceloop/*_provenance.py`, or `*_audit.py` in the
git log before those three are in place = violation.

**6. Every tier independently demoable > building everything in one go.**
The deadline is still unknown. The milestones were designed around exactly this: stopping
at any tier must still yield a demo. Do not, for the sake of later tiers, leave the current
tier in a "half-built and unrunnable" state.

---

## The Authority You Have

- **Push back on any instruction**, including mine. Bring your evidence (the implementation
  you read, the numbers you ran)
- **Refuse unreasonable scope.** If you think something is cargo cult, say so
- **Add correct things on your own.** I did not ask for `OcrUnavailable`; you added it, and
  it was right
- **Change criteria**, but say it first, show evidence, and write it into the documents —
  never change them silently

There is exactly one thing you must not do: **make the numbers look better without
evidence.**

---

## One Calibration Reference

This project's evidence base is six rounds of pre-registered experiments. Across those six
rounds, criteria were never modified after the data was seen; answers were always submitted
before scoring; wrong predictions were printed as-is (in Round Six I predicted D3 would
pass; it failed in measurement, and that went into the report).

**Your work must survive the same ruler.** Concretely:

- Speak with numbers, not adjectives
- Verify your own implementation yourself first; do not wait for me to audit it
- Say so when you find you were wrong; do not quietly fix it away
- Green tests do not mean a correct implementation — the fixture may share the same
  assumption as the implementation (that is how the `$0.00` tokenisation issue was found)

---

## Now

M2 is accepted. M3 = the four-dimensional support matrix + panel — the first time this
thing is seen by anyone. I have already validated the runtime criterion for `applicability`
for you and written it into `ARCHITECTURE.md §4`.
