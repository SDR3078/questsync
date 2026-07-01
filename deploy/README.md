# Deploying QuestSync

QuestSync is **multi-user and stateless**: each person authenticates with their
own Habitica credentials, so the deployment needs **no application secret** — just
the image and a **TLS-terminating Ingress**.

## Image
CI (`.github/workflows/ci.yml`) tests, builds, and pushes to
`ghcr.io/sdr3078/questsync` on every push to `main`. Make the GHCR package
**public** (GitHub → Packages → questsync → Package settings → Change visibility)
so the cluster can pull it without an imagePullSecret.

## Apply
Via ArgoCD (recommended):
```bash
kubectl apply -f argocd-application.yaml
```
Or directly:
```bash
kubectl apply -k k8s/
```

## ⚠️ TLS is mandatory
Users' Habitica API tokens travel in HTTP Basic auth on **every** request. Only
expose QuestSync over HTTPS. Edit `k8s/ingress.yaml` with your real hostname and
issuer; cert-manager provisions the certificate. Do **not** serve it over plain
HTTP or add it to `kustomization.yaml` until the Ingress terminates TLS.

## Image tag / GitOps note
`deployment.yaml` pins `:latest`, which ArgoCD won't re-sync on its own (the
manifest doesn't change when a new `:latest` is pushed). For real GitOps, pin the
`sha-<short>` tag CI produces and bump it on release, or run **ArgoCD Image
Updater**.
