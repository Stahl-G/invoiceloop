# DWS Signature Sealing + Viewer Coexistence: Implementation Plan (2026-08-06)

Sources: pulled live from the official documentation (not from memory); dates in each page's
`last_updated`.

- Signing: `https://www.nutrient.io/guides/dws-processor/tools-and-api/pdf-digital-signature-api.md` (2026-07-06)
- Viewer (app-provided mode): `https://www.nutrient.io/guides/dws-viewer/developer-guides/open-client-provided-documents.md` (2026-06-10)

The two items are independent of each other and can land separately. **Signatures first.**

---

## I. Digital signature sealing (priority)

### 1.1 The current gap (the project's own admission)

The verify notes at `adjudicate.py:430` say verbatim: "the bundle's authenticity is anchored in
the out-of-band published bundle sha256 — verify is not its own root of trust". The four
verification layers prove **the bundle is self-consistent**: member hashes add up, the snapshot
is recomputable, verdict bindings agree. But `MANIFEST.sha256` sits **inside** the bundle; an
attacker who tampers with a member can just recompute MANIFEST and be consistent again.
**The chain's single non-cryptographic anchor is right here.**

### 1.2 Endpoint (verified against the documentation, not yet run through)

```
POST https://api.nutrient.io/sign
Authorization: Bearer $NUTRIENT_API_KEY
-F file=@attestation.pdf
-F 'data={"signatureType":"cades","cadesLevel":"b-lt"};type=application/json'
→ returns a signed PDF
```

Omitting `appearance` / `position` / `formFieldName` = an **invisible signature** that is still
a cryptographic signature. `cades b-lt` = the long-term validation level: embedded revocation
info + a trusted timestamp — exactly what an audit bundle wants.

### 1.3 Design: add an outer envelope, touch nothing deterministic

**Key constraint**: the attestation cannot enter `MANIFEST.sha256` — what it attests is
precisely that manifest; self-containment would create a loop. So it is an **outer envelope**,
not a member.

Split into two commands, keeping `bundle` offline and deterministic as-is:

| Command | Behavior |
|---|---|
| `bundle --run R` | **Completely unchanged.** Still offline, zero network, same input same bytes |
| `seal --run R` (new) | reads `audit_bundle.zip` → builds the attestation → calls `/sign` → writes `audit_bundle.sealed.zip` |

`seal`'s three steps:

1. `manifest_sha256 = sha256(the bytes of MANIFEST.sha256 inside the zip)` — it transitively
   covers every member;
2. `attestation.json` (canonical JSON, deterministic, **containing no timestamp of ours** —
   time is provided by the signature's trusted timestamp; we do not self-report time):
   ```json
   {
     "attests": "audit_bundle",
     "manifest_sha256": "…",
     "review_snapshot_id": "…",
     "run_dir_name": "run-0001",
     "n_docs": 3,
     "invoiceloop_version": "…",
     "signature_profile": "cades/b-lt"
   }
   ```
3. Render attestation.json into a **minimal one-page PDF** (handwritten PDF syntax, ~30 lines,
   zero new dependencies, deterministic) → POST `/sign` → get `attestation.signed.pdf`;
   sealed zip = all members of the original zip + `attestation.json` + `attestation.signed.pdf`,
   **with not one byte of MANIFEST touched**.

> Alternative: use the Processor's Markdown-to-PDF to build the attestation PDF (one more deep
> DWS use), but it would make `seal` depend on one more endpoint. Recommendation: hand-write
> the PDF first and shrink the network surface to `/sign` alone.

### 1.4 The fifth verify layer

`verify_bundle`'s `layers` gains `"signature"`, keeping the existing three states
(True/False/**None**):

- no `attestation.signed.pdf` → `None`, notes record "unsealed bundle" (same handling as a v1
  bundle without the snapshot layer);
- present:
  1. recompute `sha256(MANIFEST.sha256)` and compare against `attestation.json.manifest_sha256`;
  2. compare `attestation.json`'s bytes for agreement with the content embedded in the signed
     PDF;
  3. cryptographic signature verification (CAdES chain + timestamp).
- Verification needs `cryptography` / `asn1crypto` — **made an optional dependency**:
  `pip install "invoiceloop[seal]"`. When missing, `signature: None` + the note "signature
  present but no verification dependency on this machine; unverified".
  **Per Charter Four: record the gap; never silently pass.**

The offline four-layer story stays fully intact this way; the new fifth layer is pure addition.

### 1.5 The caveat that must be written in alongside (Charter Six)

DWS signs with **its own certificate**. The signature proves:

> this attestation was signed by DWS at time T and has not been altered since.

It does **not** prove "this bundle came from InvoiceLoop" — not without a brought-along
certificate. So verify's notes should be reworded to the precise statement and **must not
become "there is now a root of trust"**:

> Fifth layer passing = the manifest digest is fixed by a DWS signature carrying a trusted
> timestamp; the signing entity is DWS, not this project — "who built the bundle" still
> requires out-of-band identity.

If this wording drifts, it loses more points than the feature earns.

### 1.6 Change list and effort

| File | Change |
|---|---|
| `invoiceloop/seal.py` (new) | attestation construction + minimal PDF writer + `/sign` client (key read only from the `NUTRIENT_API_KEY` environment, same discipline as `dws_client.py:39-41`) |
| `invoiceloop/adjudicate.py` | `verify_bundle` gains the `signature` layer; notes reworded per §1.5 |
| `invoiceloop/__main__.py` | `seal` subcommand |
| `tests/test_seal.py` (new) | after sealing, four→five layers all pass; tamper MANIFEST → signature false; tamper a member → members false; no attestation → None; no verification dependency → None + note |
| `pyproject.toml` | `[seal]` extra |

About 150 lines + tests, **half a day**. Needs one real-key end-to-end run (credit consumption
unverified).

---

## II. DWS Viewer coexistence (second priority)

### 2.1 A fact not accounted for before: the privacy concern does not hold

Viewer has two document paths; the official text:

> **App-provided documents** — Keep documents in your app or browser. Your app
> passes a file, URL, Blob, or ArrayBuffer directly to Web SDK, while DWS Viewer
> API authorizes and meters the viewer session.
> …In this app-provided flow, the document isn't uploaded to DWS.

That is, **the invoice PDF never leaves the browser**; DWS only issues a session JWT. The
privacy narrative of item C, "all processing local", is unharmed — just state honestly that
"the Viewer session authenticates to DWS; no document is uploaded".

### 2.2 Integration shape

Backend (one new route in the workbench):

```
POST https://api.nutrient.io/viewer/sessions
Authorization: Bearer $NUTRIENT_DWS_VIEWER_API_KEY
body: {}            # allowed_documents omitted = app-provided mode
→ {"jwt": "…"}
```

Frontend (adjudication page):

```js
await NutrientViewer.load({
  container: "#viewer",
  session: "<jwt>",
  document: "/files/<run>/pages/<doc>.pdf",   // the workbench's existing local route
});   // licenseKey omitted — the session is the authorization
```

### 2.3 Discipline: it must be an optional surface; defaults unchanged

- **The default remains the self-built panel** (full-page render + bbox overlay + gate chips +
  fast paths) — that is the substance of F's 13 points and cannot be swapped out;
- Viewer is a toggle button on the adjudication page; `NUTRIENT_DWS_VIEWER_API_KEY`
  unset / no network → the button does not appear and the page behaves byte-for-byte
  identically to today;
- **The `demo` path's zero-API nature must be preserved** — it is the precondition for judges
  to run it through on their own machines.

### 2.4 Costs, stated honestly

- every load consumes a viewer session (monthly quota applies);
- requires pulling in the Web SDK's JS assets (CDN or vendored) — the workbench is currently
  pure stdlib with no external resources, and this would break offline capability, **which is
  why it can only live behind a flag**;
- the docs state plainly: the session must be created by the backend, is not refreshed after
  load, and `setSession()` is unsupported in app-provided mode;
- functionally, Viewer offers annotation/forms/collaboration, none of which InvoiceLoop needs;
  **the real benefit is rendering and zoom for multi-page documents, plus the visibility of
  being named by the organizer.**

### 2.5 Change list and effort

| File | Change |
|---|---|
| `invoiceloop/workbench.py` | `POST /viewer-session` route (reusing the existing Host allowlist + Origin checks); a toggle button and a container div added to the adjudication page |
| `invoiceloop/workbench_style.py` | viewer container styles |
| `tests/test_workbench.py` | without a key the button does not render and the page is equivalent to today; with a key the route exists and no key leaks to the frontend |

About 100 lines, **half a day**. The risk concentrates on "don't break the offline demo".

---

## III. Order and acceptance

1. **Signatures first**: it fills a gap the project itself admits, is a cryptographic upgrade,
   and lines up directly with the brief's twice-named "digitally sign the result so its
   authenticity is provable";
2. **Then Viewer**: an optimization surface + organizer preference; the default path changes
   zero;
3. Both need one real-key end-to-end run, and the caveats (§1.5, §2.3) written into the README
   side by side with the feature.

**Acceptance criteria** (written before doing):

- the sealed bundle `verify`es five layers on a **disconnected** machine; a single-byte tamper
  of MANIFEST → `signature: false`;
- with the optional dependency missing, `signature: None` and notes explaining unverified —
  **it must never report true**;
- with `NUTRIENT_DWS_VIEWER_API_KEY` unset, the adjudication page HTML is **byte-for-byte
  identical** to before this change;
- the `demo` flow remains zero API, zero external resources.
