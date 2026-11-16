# Photo Service : déploiement Kubernetes

Projet du cours de systèmes distribués et scalabilité (ECAM) : une application de stockage de photos, livrée en continu
sur Kubernetes, avec base de données répliquée et shardée, cache, monitoring et autoscaling.

## L'application

Application web (Flask) : création de compte et connexion, envoi de photos, détection de doublons, comparaison de deux photos, albums privés
ou partagés avec d'autres utilisateurs.

## Ce que montre le projet

| Sujet | En bref |
|---|---|
| Environnements | `dev`, `test` et `prod`, séparés par namespace dans un même cluster |
| Livraison continue | un `git push` sur `main` lance les tests, déploie en `test`, vérifie (smoke-test), puis déploie en `prod` après validation, sans interruption |
| Base de données | PostgreSQL géré par CloudNativePG : 2 shards, chacun avec un primaire et une réplique (basculement automatique) |
| Migrations | fichiers SQL numérotés, appliqués sur chaque shard par un Job avant le déploiement de la nouvelle version |
| Cache | Varnish, 2 pods, devant l'application (fichiers statiques) |
| Point d'entrée | un seul contrôleur Ingress nginx |
| Monitoring et scaling | metrics-server et tableau de bord Headlamp (changement du nombre de pods) ; autoscaling horizontal (HPA, de 3 à 6 pods) |
| Cloud | déploiement sur le cluster OVH de l'équipe (droits limités à un namespace) |

## Par où commencer

La documentation complète est dans [`docs/`](docs/README.md). Pour découvrir le projet et tout installer :
[`docs/05-onboarding.md`](docs/05-onboarding.md).

| Section | Fichier |
|---|---|
| Installation du cluster (local) et migration vers le cloud | [`docs/01-cluster.md`](docs/01-cluster.md) |
| Pipeline CI/CD | [`docs/02-ci-cd.md`](docs/02-ci-cd.md) |
| Base de données, migrations, cache | [`docs/03-database.md`](docs/03-database.md) |
| Monitoring et scaling | [`docs/04-monitoring-scaling.md`](docs/04-monitoring-scaling.md) |
| Onboarding | [`docs/05-onboarding.md`](docs/05-onboarding.md) |

## Organisation du dépôt

```text
app/          application Flask, migrations SQL, Dockerfile
tests/        tests unitaires (pytest)
k8s/          manifests Kubernetes (base, overlays par environnement, composants de plateforme)
scripts/      deploy.sh, smoke-test.sh, watch.sh, loadtest.sh, shard-demo.sh
.github/      pipeline GitHub Actions
docs/         documentation
```

## Essayer en local

Prérequis, installation du cluster et premier déploiement : voir [`docs/05-onboarding.md`](docs/05-onboarding.md) (section 3). Une fois
l'environnement `test` déployé, l'application répond sur `http://test.photo.localhost/` et le tableau de bord sur `http://headlamp.localhost`.

Lancer les tests : `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest`