# Onboarding : arriver sur le projet

> Pour une personne qui découvre le dépôt : comprendre l'organisation, tout installer, tout lancer, contribuer.

## 1. Le projet en deux minutes

Une application de **stockage de photos** (envoi, liste, détection de doublons, comparaison) déployée sur Kubernetes. Elle illustre : une
base de données **répliquée et shardée**, un **cache**, un **déploiement continu sans interruption** (test puis production), un **tableau de bord**
de monitoring avec scaling, et un **autoscaling**. Le tout tourne sur un cluster local (kind).

Qui s'occupe de quoi (pour savoir à qui poser une question) :

| Domaine | Fichiers principaux |
|---|---|
| Application, migrations, pipeline, HPA, scripts de déploiement | `app/`, `tests/`, `.github/`, `scripts/deploy.sh`, `smoke-test.sh`, `watch.sh`, `k8s/base/hpa/` |
| Base de données, cache, installation du cluster, monitoring | `k8s/base/db-cluster*/`, `k8s/base/cache/`, `k8s/platform/`, `scripts/shard-demo.sh`, `kind-config.yaml` |

## 2. Carte du dépôt

```text
.github/workflows/ci.yml     la pipeline (test, déploiement test, smoke-test, déploiement prod)
app/                         l'application Flask : app.py (routes), db.py (accès aux shards), migrate.py,
                             migrations/ (SQL numéroté), static/index.html (interface web), Dockerfile
tests/                       tests unitaires (pytest)
scripts/                     deploy.sh, smoke-test.sh, watch.sh, shard-demo.sh
k8s/base/                    manifests communs : deployment, service, ingress, migrate-job, hpa/, cache/,
                             db-cluster/ et db-cluster-s1/ (les deux shards), db/ (première brique, dev)
k8s/overlays/{dev,test,prod} ce qui change par environnement (namespace, hôte, tag d'image...)
k8s/platform/                composants installés une fois : metrics-server, headlamp, cnpg (opérateur de base)
kind-config.yaml             configuration du cluster local
secrets/                     (ignoré par Git) identifiants locaux, kubeconfig d'un cluster distant
docs/                        cette documentation
```

Le principe Kustomize : `base/` décrit ce qui est commun, chaque **overlay** décrit ce qui change (`kubectl kustomize k8s/overlays/test` affiche le résultat assemblé).

## 3. Installation pas à pas

1. **Outils** : Docker Desktop (au moins 6 Gio de mémoire), `kind`, `kubectl`, `kustomize`, `git`, `python3`.
2. **Cloner** le dépôt **hors d'un dossier synchronisé** (iCloud, Dropbox) : la synchronisation corrompt les fichiers internes de Git (erreurs `mmap failed`).
   ```bash
   git clone https://github.com/ibtihal-mrn/Distrubuted_Systems_Project.git ~/dev/Distrubuted_Systems_Project
   cd ~/dev/Distrubuted_Systems_Project
   ```
3. **Lancer les tests** :
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-dev.txt
   .venv/bin/python -m pytest
   ```
4. **Créer le cluster et installer la plateforme** : `docs/01-cluster.md`, sections 3 à 5 (cluster, contrôleur Ingress, metrics-server, Headlamp, opérateur de base de données).
5. **Déployer l'environnement de test** :
   ```bash
   kubectl --context kind-photo apply -f k8s/overlays/test/namespace.yaml
   kubectl --context kind-photo create secret generic photo-secret -n test \
     --from-literal=SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
   ./scripts/deploy.sh test local1
   git checkout k8s/overlays/test/kustomization.yaml     # le script change le tag d'image : ne pas le commiter
   ```
   Le Secret `photo-secret` (clé de signature des sessions) doit exister dans chaque namespace avant le déploiement : aucun script ne le crée.
6. **Essayer** :
   ```bash
   curl -s http://test.photo.localhost/health                                  # ok
   curl -s -F "photo=@une-image.jpg" http://test.photo.localhost/photos        # envoie une photo
   curl -s http://test.photo.localhost/photos                                  # la liste
   curl -s http://test.photo.localhost/duplicates                              # les doublons
   ```
   L'interface web : `http://test.photo.localhost/ui`.
7. **Tableau de bord** : `http://headlamp.localhost`, avec un token (`kubectl --context kind-photo create token headlamp-operator -n kube-system --duration=1h`).

## 4. Travailler à deux sur le code

- **Une branche par tâche**, créée depuis `main` à jour : `git fetch origin` puis `git switch -c <ma-branche> origin/main`.
- **Une pull request relue par l'autre personne** avant fusion.
- **`main` déclenche la pipeline** : une fusion sur `main` déploie en `test`, puis en `prod` après validation. Ne fusionnez que ce qui est prêt, et prévenez avant une
  fusion qui nécessite une installation préalable sur le cluster du runner (par exemple l'opérateur de base de données).
- **Jamais de secret dans le dépôt** : mots de passe, tokens, kubeconfig. Le dossier `secrets/` et les fichiers `.env*` sont ignorés ; vérifiez avec `git status`
  avant chaque commit (et `git check-ignore -v secrets/` si un doute subsiste).
- Un script ou une commande qui modifie un fichier suivi par Git (le tag d'image dans un overlay) : ne commitez pas ce changement.

## 5. Commandes utiles

| Besoin | Commande |
|---|---|
| Où suis-je (contexte) ? | `kubectl config current-context` (doit afficher `kind-photo`) |
| Voir ce qui tourne | `kubectl --context kind-photo get pods -n <dev\|test\|prod>` |
| Charge actuelle | `kubectl --context kind-photo top pods -n test` |
| État des bases | `kubectl --context kind-photo get cluster -n test` |
| Journaux d'un pod | `kubectl --context kind-photo logs <pod> -n <env>` |
| Voir un overlay assemblé | `kubectl kustomize k8s/overlays/test` |
| Tester sans appliquer | `kubectl --context kind-photo apply -k k8s/overlays/test --dry-run=server` |
| Mesurer un déploiement | `./scripts/watch.sh test` pendant un déploiement |
| Démontrer le sharding | `./scripts/shard-demo.sh` |

## 6. Pièges rencontrés (et comment les éviter)

| Piège | Explication | À faire |
|---|---|---|
| Une commande agit sur un autre cluster | Docker Desktop remet le contexte sur `docker-desktop` | `--context kind-photo` partout |
| `-n "$ENV"` agit sur `default` | une variable vide devient `-n ""` | écrire le namespace, ou `${1:?message}` dans un script |
| `zsh: parse error` en collant `<id>` | les chevrons sont des redirections pour le shell | remplacer le texte entre chevrons par la vraie valeur |
| `kubectl get a,b -w` refusé | `-w` n'accepte qu'un seul type d'objet | une commande par type |
| `port-forward` ne répartit pas la charge | il reste attaché à un seul pod | tester par un pod ponctuel dans le cluster, ou par l'Ingress |
| `curl -I` ne montre pas le cache | `-I` envoie `HEAD` | `curl -s -D - -o /dev/null <url>` |
| En-têtes qui s'écrasent à l'affichage | retours chariot (`\r`) | `... \| tr -d '\r'` |
| `Too long` en installant l'opérateur | application classique | `kubectl apply --server-side` |
| `no matches for kind "Cluster"` | l'opérateur n'est pas installé | l'installer avant d'appliquer les overlays |
| Erreurs `mmap failed` de Git | dossier synchronisé par iCloud | travailler dans `~/dev` |
| Le runner ne prend aucun job | runner hors ligne | l'allumer ; Docker lancé ; veille désactivée |

## 7. Scénario de démonstration complet

1. **Pipeline** : un `git push` sur `main`, puis suivre l'onglet *Actions* (test, déploiement en test, smoke-test, validation, production).
2. **Zéro interruption** : `./scripts/watch.sh prod` pendant le déploiement : aucune requête en erreur ; la version affichée change.
3. **Migration** : ajouter un fichier `app/migrations/002_*.sql` compatible avec l'ancienne version ; il s'applique sur les deux shards avant le rollout.
4. **Base répliquée** : `get cluster`, supprimer le primaire d'un shard, voir la réplique promue et l'application continuer.
5. **Sharding** : `./scripts/shard-demo.sh`, puis envoyer deux fois la même photo : même shard, doublon signalé.
6. **Cache** : deux requêtes sur une photo (MISS puis HIT), `/health` jamais mis en cache.
7. **Monitoring et scaling** : Headlamp (charge, changement du nombre de replicas, refus d'une action interdite), puis l'HPA sous charge.
