# Deploying QuestSync

QuestSync is **multi-user and stateless** — each person authenticates with their own
Habitica credentials, so the deployment needs **no application secret** and **no
persistent volume**. You just run the (public) image and route **HTTPS** to it.

## Manifests

`deploy/k8s/` is a Kustomize base:

| File | |
|------|--|
| `deployment.yaml` | the QuestSync pod — non-root, read-only rootfs, drops all caps, `seccompProfile: RuntimeDefault` (PodSecurity `restricted`-compatible); pins an immutable image tag |
| `service.yaml` | ClusterIP on `:5232` |
| `networkpolicy.yaml` | default-deny + allow ingress from your ingress controller and egress to DNS/HTTPS |
| `ingress.yaml` | **template only** — not in `kustomization.yaml`; set your host + TLS and opt it in, or route to the Service another way |

```bash
kubectl apply -k deploy/k8s/          # deployment + service + networkpolicy
```

## Image

CI (`.github/workflows/ci.yml`) builds and pushes `ghcr.io/sdr3078/questsync` (a **public**
package — no imagePullSecret) on every push to `main`, tagging `:latest`, an immutable
`:sha-<short>`, and `:v*` on releases.

Pin an immutable `:sha-<short>` or `:v*` tag in `deployment.yaml` rather than `:latest`
(which drifts silently and re-pulls on every restart with no audit trail).

## ⚠️ TLS is mandatory

Users' Habitica API tokens (password-equivalent) travel in HTTP Basic auth on **every**
request. Only ever expose QuestSync over HTTPS — via an ingress + cert (e.g. cert-manager)
or a tunnel that terminates TLS. If a reverse proxy re-encrypts to the origin, make sure it
verifies **by hostname against a valid cert** — never disable cert verification or use a
plaintext origin hop.

## Hardening for public exposure

QuestSync validates any Habitica user-id/token pair by calling Habitica live, from the
pod's egress IP — so an open, unthrottled endpoint is a credential-validation oracle and a
shared-egress DoS risk (spraying stolen pairs can get your egress IP rate-limited by
Habitica, breaking every user). If you expose it to the internet, add **rate-limiting** and
a **WAF** at your edge/ingress.

## Local development

See the repo root [`README.md`](../README.md) — `docker compose up`.
