#!/usr/bin/env bash
# Usage : watch.sh <test|prod>
# Envoie des requêtes en continu et compte les erreurs. Ctrl+C pour afficher le bilan.
URL="http://${1:-prod}.photo.localhost/"
ok=0
ko=0
trap 'echo; echo "Bilan : $ok requêtes OK, $ko en erreur"; exit 0' INT

while true; do
  resp=$(curl -s -m 2 -w ' HTTP:%{http_code}' "$URL" || true)
  code="${resp##*HTTP:}"
  if [ "$code" = "200" ]; then
    ok=$((ok + 1))
    version=$(echo "$resp" | grep -o '"version":"[^"]*"' || true)
    echo "$(date +%T) OK  $version"
  else
    ko=$((ko + 1))
    echo "$(date +%T) ERREUR (code $code)"
  fi
  sleep 0.2
done
