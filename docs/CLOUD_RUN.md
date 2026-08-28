# Cloud Run deployment

## What it gives you, and what it does not

| | |
|---|---|
| ✅ The "Google Cloud infrastructure service" requirement | A Cloud Run revision and a `.run.app` URL |
| ✅ Something a reader can click | The demo workspace is baked into the image; the queue opens on a cold start |
| ❌ **Not** persistence | Cloud Run instances are ephemeral; the filesystem is gone at recycle |
| ❌ **Not** real human-in-the-loop | The public instance is read-only; real adjudication happens on a local writable workbench |
| ❌ **Not** a better product | The trust kernel is deterministic Python and behaves identically on a laptop |

The honest external claim is "a synthetic demo is deployed on Cloud Run." Not
"the system runs in the cloud", and not "cloud persistence".

## The public instance must be read-only

The workbench has nine write routes. `POST /decide` appends to the **adjudication
ledger** — the record that *a person looked at this and judged*.
`--allow-unauthenticated` plus a writable service means anyone on the internet can
forge that testimony.

So the container entrypoint passes `--read-only` by default: every POST returns
403, and every page carries a banner explaining why. `INVOICELOOP_READ_ONLY=0`
turns it off, but that is **only defensible behind private IAM**.

For a demo recording, use two shots: the local writable workbench for the
human-in-the-loop segment (a real adjudication happening), and the `.run.app` URL
for the deployment segment. Both are true.

## There is no GCS

The demo workspace is baked in at `docker build` time by `invoiceloop demo`, so
nothing is fetched at run time. An optional GCS pull used to exist and was deleted
outright:

- `python3 -m invoiceloop cloud pull … || true` swallowed everything — a missing
  SDK, a failed credential, a corrupt archive — and then **silently substituted a
  demo workspace for the real data the operator asked for.** That is precisely the
  failure this project exists to prevent.
- `tar.extractall(dest)` filtered no members — path traversal.
- The advertised "persistence" was never real: the entrypoint pulled and never
  pushed, so anything written in the container was lost at recycle anyway.

Deleting the path removed all three problems and one service. Cloud Run alone
satisfies the requirement.

## Verify the image locally

```bash
docker build -t invoiceloop:local .
docker run --rm -p 8080:8080 invoiceloop:local
curl -fsS http://127.0.0.1:8080/healthz                                          # in-container path
curl -fsS -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8080/decide  # expect 403
```

## Deploy

```bash
# once, on a billing-enabled project
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

./scripts/deploy_cloud_run.sh
# or: PROJECT=… REGION=… SERVICE=… ./scripts/deploy_cloud_run.sh
```

The script always sets `INVOICELOOP_READ_ONLY=1`. That is what makes
`--allow-unauthenticated` safe.

## Binding and probes

- Local CLI defaults to `--host 127.0.0.1` (loopback), unchanged
- The container entrypoint uses `--host 0.0.0.0 --port $PORT` and
  `--allowed-host .run.app`
- `GET /_health` (external) and `GET /healthz` (in-container) are answered before
  the Host gate, and neither runs `doctor` — that would look for the research corpus
- **`/healthz` does not work from outside on Cloud Run.** Google's frontend
  intercepts it before the request reaches the service and returns its own 404.
  Measured on the live deployment: `/healthzz`, `/_health`, `/livez` and `/nope`
  all reached the application, and only `/healthz` did not. The in-container
  `HEALTHCHECK` hits `127.0.0.1` and never crosses the frontend, so it is unaffected.
- **The Host suffix allowlist is not authentication.** It blocks DNS rebinding.
  Do not use it as access control.

## Evidence

A deployment must leave behind: project, service, revision, image digest, URL,
timestamp, remote smoke output, and a console screenshot, under
`docs/evidence/cloud_run_<date>/`. Until those exist, nothing anywhere should say
the Google Cloud requirement is satisfied.

See [`evidence/cloud_run_2026-08-07/`](evidence/cloud_run_2026-08-07/README.md).

## Cloud Run Job (the Arm U unattended arm, P2, 2026-08-28)

The public `.run.app` service and the Job are **the same image, two entrypoints**:

| | Read-only workbench (since 2026-08-07) | Job `invoiceloop-unattended` |
|---|---|---|
| Entrypoint | `/cloud_entrypoint.sh` → `workbench --read-only` | `bash scripts/run_unattended_job.sh` |
| Exposure | public URL, all nine write routes 403 | **no URL**; IAM-private, triggerable only within the project |
| Credentials | none (zero-API demo) | the Job SA's ADC (Vertex AI); no key is installed |
| Artifacts | baked into the image, lost at instance recycle | uploaded to GCS before the process ends; upload failure = exit 1 (blocking) |
| What it proves | deployment | **a real unattended run landed in the bucket** |

Job semantics (see the `scripts/run_unattended_job.sh` header): exit code 0 means
"this run completed and its evidence is in the bucket", **not** "a document was
released" — release remains the policy's and the approver's call. One command
deploys, executes, and freezes evidence:

```bash
./scripts/deploy_cloud_run_job.sh
# evidence lands under docs/evidence/cloud_run_job_<date>/ (job/execution configs, logs, GCS listing)
```

IAM required: the Job's default SA holds `roles/storage.objectAdmin` (scoped to
the artifacts bucket) and `roles/aiplatform.user`; the script warns when a grant
fails, and a Vertex 403 will show up explicitly in the execution log.
