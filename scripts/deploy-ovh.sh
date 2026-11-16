#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:?Usage: deploy-ovh.sh <tag>}"
IMAGE="${IMAGE:-ghcr.io/ibtihal-mrn/photo-service}"                 # en minuscules
KUBECONFIG_FILE="${KUBECONFIG_FILE:?Chemin du kubeconfig requis}"   # fourni par la pipeline
NS="${NS:-team2}"

# 1. image multi-architecture, publiée dans le registre
docker buildx build --platform linux/amd64,linux/arm64 \
  --build-arg APP_VERSION="$TAG" -t "$IMAGE:$TAG" --push ./app

# 2. le tag dans l'overlay (même mécanisme que deploy.sh)
(cd k8s/overlays/ovh && kustomize edit set image ghcr.io/ayoub21061/photo-service="$IMAGE:$TAG")

# 3. appliquer l'overlay sur le cluster du prof
kubectl --kubeconfig="$KUBECONFIG_FILE" apply -n "$NS" -k ./k8s/overlays/ovh

# 4. attendre le rollout
kubectl --kubeconfig="$KUBECONFIG_FILE" rollout status deployment/photo-service -n "$NS" --timeout=180s
# 5. tester l'URL publique, avec quelques essais
for i in 1 2 3 4 5 6; do
  if [ "$(curl -fsS http://team2.laboinfo-ecam.be/health 2>/dev/null)" = "ok" ]; then
    echo "OK : team2.laboinfo-ecam.be répond"
    exit 0
  fi
  echo "Tentative $i : pas encore prêt, nouvelle tentative dans 5 s"
  sleep 5
done
echo "ÉCHEC : team2.laboinfo-ecam.be ne répond pas"
exit 1