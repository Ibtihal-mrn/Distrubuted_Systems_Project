#!/usr/bin/env bash
set -euo pipefail
ENV="${1:?Usage: smoke-test.sh <test|prod>}"
URL="http://$ENV.photo.localhost/health"

for i in 1 2 3 4 5; do
  if [ "$(curl -fsS "$URL" 2>/dev/null)" = "ok" ]; then
    echo "OK : $URL répond"
    exit 0
  fi
  echo "Tentative $i : pas encore prêt, nouvelle tentative dans 3 s"
  sleep 3
done
echo "ÉCHEC : $URL ne répond pas"
exit 1
