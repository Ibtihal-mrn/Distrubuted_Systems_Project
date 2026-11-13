# Applique les fichiers SQL de migrations/ sur chaque shard, dans l'ordre.

# Variables d'environnement : SHARD0_DSN, SHARD1_DSN

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
SHARD_VARS = ["SHARD0_DSN", "SHARD1_DSN"]


def migrate_shard(numero, dsn):
    fichiers = sorted(MIGRATIONS_DIR.glob("*.sql"))
    appliquees = 0

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Le carnet de bord de cette base
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version TEXT PRIMARY KEY,"
                " applied_at TIMESTAMP NOT NULL DEFAULT now())"
            )
            cur.execute("SELECT version FROM schema_migrations")
            deja_faites = {ligne[0] for ligne in cur.fetchall()}
        conn.commit()

        for fichier in fichiers:
            if fichier.name in deja_faites:
                continue
            # Le SQL du fichier et l'inscription dans le carnet sont validés ensemble
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(fichier.read_text())
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (fichier.name,),
                    )
            print(f"shard {numero} : {fichier.name} appliqué")
            appliquees += 1

    if appliquees == 0:
        print(f"shard {numero} : rien à faire")


def main():
    for numero, variable in enumerate(SHARD_VARS):
        dsn = os.environ.get(variable)
        if not dsn:
            sys.exit(f"Variable d'environnement manquante : {variable}")
        migrate_shard(numero, dsn)


if __name__ == "__main__":
    main()

# Pour tester en local (conteneurs shard0 sur 5432 et shard1 sur 5433) :
#   export SHARD0_DSN="postgresql://postgres:dev@localhost:5432/photos"
#   export SHARD1_DSN="postgresql://postgres:dev@localhost:5433/photos"
#   python app/migrate.py