# Deploying QuestSync

## Image
CI (`.github/workflows/ci.yml`) tests and builds the image. Push it to a registry
your cluster can pull (e.g. `ghcr.io/sdr3078/questsync:latest`) and update the
`image:` in `k8s/deployment.yaml` if needed.

## Secret (Habitica credentials)
Never commit the plaintext token. Create a sealed secret:

```bash
kubectl create secret generic questsync-habitica \
  --from-literal=HABITICA_USER_ID=xxxxxxxx \
  --from-literal=HABITICA_API_TOKEN=xxxxxxxx \
  --dry-run=client -o yaml | kubeseal -o yaml > k8s/sealedsecret.yaml
```
Add `sealedsecret.yaml` to `k8s/kustomization.yaml` once created.

## Apply
Via ArgoCD (recommended):
```bash
kubectl apply -f argocd-application.yaml
```
Or directly:
```bash
kubectl apply -k k8s/
```

## ⚠️ Before exposing publicly
The bundled config uses `auth = none`. Enable DAV auth (htpasswd or a custom
`BaseAuth`) **before** adding `k8s/ingress.yaml`. Until then, reach it in-cluster
or with `kubectl port-forward svc/questsync 5232:5232`.
