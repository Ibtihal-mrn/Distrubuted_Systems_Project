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

# Écrit le tag dans l'overlay : Deployment ET Job utiliseront cette image
(cd k8s/overlays/"$ENV" && kustomize edit set image photo-service:"$TAG")

# 1. Supprime l'ancien Job : Kubernetes interdit de modifier un Job existant
#    (son image change à chaque déploiement). --ignore-not-found = pas d'erreur s'il n'existe pas.
kubectl delete job photo-migrate -n "$ENV" --ignore-not-found --context kind-photo

# 2. Applique UNIQUEMENT le Job (-l = sélection par étiquette), puis attend sa fin.
#    Le Deployment n'est pas encore touché : l'ancienne version continue de servir.
kubectl apply -k ./k8s/overlays/"$ENV" -l component=migration --context kind-photo
if ! kubectl wait --for=condition=complete job/photo-migrate -n "$ENV" --timeout=180s --context kind-photo; then
  echo "Migration en échec, déploiement annulé. Logs :"
  kubectl logs job/photo-migrate -n "$ENV" --context kind-photo || true
  exit 1   # le pipeline devient rouge, le rollout n'a pas lieu
fi

# 3. Migration réussie : applique tout le reste et attend le rollout
kubectl apply -k ./k8s/overlays/"$ENV" --context kind-photo
kubectl rollout status deployment/photo-service -n "$ENV" --timeout=120s --context kind-photo