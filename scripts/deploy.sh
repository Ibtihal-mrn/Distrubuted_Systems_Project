#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

ENV="${1:?Usage: deploy.sh <test|prod> <tag>}"
TAG="${2:?Please provide a tag for the deployment.}"

case "$ENV" in
  test|prod) ;;
  *) echo "Environnement inconnu : $ENV (attendu : test ou prod)"; exit 1 ;;
esac

# Construit l'image seulement si elle n'existe pas encore (en prod, c'est celle de test)
if docker image inspect photo-service:"$TAG" >/dev/null 2>&1; then
  echo "Image photo-service:$TAG déjà présente, pas de reconstruction."
else
  docker build --build-arg APP_VERSION="$TAG" -t photo-service:"$TAG" ./app
fi
kind load docker-image photo-service:"$TAG" --name photo

(cd k8s/overlays/"$ENV" && kustomize edit set image photo-service:"$TAG")
kubectl apply -k ./k8s/overlays/"$ENV" --context kind-photo
kubectl rollout status deployment/photo-service -n "$ENV" --timeout=120s --context kind-photo
