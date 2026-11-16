# Applique les fichiers SQL de migrations/ sur chaque shard, dans l'ordre.

# Variables d'environnement : SHARD0_DSN, SHARD1_DSN

import os                            # lire les variables d'environnement
import sys                           # sys.exit : arrêter le script avec un message
from pathlib import Path             # manipuler des chemins de fichiers

import psycopg                       # le pilote PostgreSQL

MIGRATIONS_DIR = Path(__file__).parent / "migrations"   # le dossier migrations/ à côté de ce fichier
SHARD_VARS = ["SHARD0_DSN", "SHARD1_DSN"]               # noms des variables contenant l'adresse de chaque base
                                                        # (données par le Job, depuis les Secrets de CloudNativePG)

def migrate_shard(numero, dsn):      # migre UNE base (shard 0 ou 1)
    fichiers = sorted(MIGRATIONS_DIR.glob("*.sql"))   # tous les .sql, triés par NOM : numérote 001_, 002_...
    appliquees = 0                   # compteur, pour le message final

    with psycopg.connect(dsn) as conn:           # connexion à la base ; fermée à la sortie du bloc
        with conn.cursor() as cur:
            # Le « carnet de bord » : une table qui liste les migrations déjà faites
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("     # créée seulement si elle n'existe pas
                " version TEXT PRIMARY KEY,"                          # nom du fichier appliqué (unique)
                " applied_at TIMESTAMP NOT NULL DEFAULT now())"       # date d'application
            )
            cur.execute("SELECT version FROM schema_migrations")      # lit le carnet
            deja_faites = {ligne[0] for ligne in cur.fetchall()}      # ensemble des noms déjà appliqués
        conn.commit()                # valide la création du carnet

        for fichier in fichiers:     # dans l'ordre 001, 002, 003...
            if fichier.name in deja_faites:
                continue             # déjà appliqué : on le saute
            # Tout ce qui suit est une TRANSACTION : tout réussit, ou rien n'est enregistré
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(fichier.read_text())          # exécute le SQL du fichier
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",   # l'inscrit dans le carnet
                        (fichier.name,),
                    )
            print(f"shard {numero} : {fichier.name} appliqué")   # visible dans les logs du Job
            appliquees += 1

    if appliquees == 0:
        print(f"shard {numero} : rien à faire")    # c'est le message dans les logs du Job

def main():
    for numero, variable in enumerate(SHARD_VARS):   # shard 0 puis shard 1
        dsn = os.environ.get(variable)               # lit l'adresse de la base dans l'environnement
        if not dsn:
            sys.exit(f"Variable d'environnement manquante : {variable}")   # arrêt avec un message d'erreur
        migrate_shard(numero, dsn)

if __name__ == "__main__":           # exécuté seulement quand on lance « python migrate.py » 
    main()

# Pour tester en local (conteneurs shard0 sur 5432 et shard1 sur 5433) :
#   export SHARD0_DSN="postgresql://postgres:dev@localhost:5432/photos"
#   export SHARD1_DSN="postgresql://postgres:dev@localhost:5433/photos"
#   python app/migrate.py