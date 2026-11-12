#!/usr/bin/env bash
set -euo pipefail

NS=dev
SHARDS=(photos-s0 photos-s1)
N=2

primary_of() {   # $1 = cluster ; affiche le nom du pod primaire
  kubectl --context kind-photo get cluster "$1" -n "$NS" -o jsonpath='{.status.currentPrimary}'
}

sql() {          # $1 = cluster, $2 = requête SQL
  kubectl --context kind-photo exec "$(primary_of "$1")" -n "$NS" -c postgres -- psql -d photos -tA -c "$2"
}

shard_for() {     # $1 = nom ; affiche le numéro de shard (0 ou 1)
    local sha
    sha=$(echo -n "$1" | shasum -a 256 | cut -c1-8)
    echo $((16#$sha % N)) 
}

# 1. créer la table dans chaque shard (relançable)
CREATE_TABLE_SQL="CREATE TABLE IF NOT EXISTS shard_demo (nom TEXT PRIMARY KEY);"
# 2. pour chaque nom : calculer le shard, insérer dans le bon cluster
for shard in "${SHARDS[@]}"; do
  sql "$shard" "$CREATE_TABLE_SQL"
done
for nom in "photo1" "photo2" "photo3" "photo4" "photo5" "photo6"; do
  shard=$(shard_for "$nom")
  sql "${SHARDS[$shard]}" "INSERT INTO shard_demo (nom) VALUES ('$nom') ON CONFLICT DO NOTHING;"
done

# 3. afficher le nombre de lignes par shard
for shard in "${SHARDS[@]}"; do
  count=$(sql "$shard" "SELECT COUNT(*) FROM shard_demo;")
  echo "Shard $shard : $count lignes"
done