# Cloud Run deployment evidence (2026-08-07)

| | |
|---|---|
| Project | `airy-decorator-361514` |
| Region | `asia-southeast1` |
| Service | `invoiceloop` |
| Revision | `invoiceloop-00002-tnk` |
| Image | `…/cloud-run-source-deploy/invoiceloop@sha256:343761e2…c72b1bdc` |
| URL | https://invoiceloop-478275522139.asia-southeast1.run.app |
| Alias URL | https://invoiceloop-h6ff2yrz2a-as.a.run.app |
| First deployed | 2026-08-07T11:17:51Z |
| Smoke run | 2026-08-07T11:32:42Z |

Built by Cloud Build (`gcloud run deploy --source .`); image in Artifact Registry.

## Files

| File | Contents |
|---|---|
| `deployment.json` | project / revision / image digest / env / ingress |
| `iam_policy.json` | `allUsers` → `roles/run.invoker` |
| `remote_smoke.txt` | Measured status codes for the probe, the read paths, and all nine write routes |

## Security posture

`allUsers` can invoke this service. **That is only defensible because the instance
is read-only.** `INVOICELOOP_READ_ONLY=1` is set on the revision (see
`deployment.json`), all nine write routes return 403 from the public internet (see
`remote_smoke.txt`), and every page carries a banner saying so.

The adjudication ledger records that *a person looked at this and judged*. A
publicly writable instance would let anyone forge that testimony, so the public
instance accepts no writes at all. Real human review happens only on a locally-run
writable workbench.

## A platform behaviour worth recording

**`/healthz` is not reachable from outside on Cloud Run.** Google's frontend
intercepts it before the request reaches the service and returns its own 404 page
— no `server: Google Frontend` header on the response, and no entry in the
container's access log.

This was not a guess. On the same deployment, `/healthzz`, `/_health`, `/livez`
and `/nope` all reached the application and were answered with *our* 404. Only
`/healthz` did not arrive. So the path is taken by the platform, not misrouted by us.

The external probe therefore answers on `/_health`. The in-container `HEALTHCHECK`
hits `127.0.0.1` and never crosses the frontend, so `/healthz` still works there;
both paths are served.

## What this proves, and what it does not

**Proves:** the Google Cloud infrastructure requirement has a physical artifact —
a revision, an image digest, a reachable URL, and a remote smoke run.

**Does not prove:**
- Not persistence. Cloud Run instances are ephemeral; the filesystem is gone at recycle.
- Not real human-in-the-loop. Nobody can adjudicate anything on a read-only instance.
- Not a better product. The trust kernel is deterministic Python and behaves identically locally.

The honest external claim is "a synthetic demo is deployed on Cloud Run."

## Reproduce

```bash
gcloud run services describe invoiceloop \
  --project=airy-decorator-361514 --region=asia-southeast1
curl -fsS https://invoiceloop-478275522139.asia-southeast1.run.app/_health
curl -o /dev/null -w '%{http_code}\n' -X POST \
  https://invoiceloop-478275522139.asia-southeast1.run.app/decide   # expect 403
```
