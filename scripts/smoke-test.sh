#!/usr/bin/env bash
set -euo pipefail # le script s'arrête à la première erreur
ENV="${1:?Usage: smoke-test.sh <test|prod>}" # argument test ou prod sur qui on exécute le script
URL="http://$ENV.photo.localhost/health" # l'url qu'on interroge

for i in 1 2 3 4 5; do # 5 tentatives 
  if [ "$(curl -fsS "$URL" 2>/dev/null)" = "ok" ]; then # on fait un curl censé renvoyer ok
    echo "OK : $URL répond" # si ok, tout est bon
    exit 0 # le job passe au vert 
  fi
  echo "Tentative $i : pas encore prêt, nouvelle tentative dans 3 s" 
  sleep 3 # on recommence dans 3 secondes si pas bon 
done
echo "ÉCHEC : $URL ne répond pas"
exit 1 # le test échoue 
