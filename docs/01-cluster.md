# Installation du cluster

> Partie « Installation du cluster » : mise en place locale, puis guide de migration vers un cluster cloud.

## 1. Vue d'ensemble

Le projet tourne sur **un cluster Kubernetes local** créé avec **kind** (Kubernetes dans Docker). Un seul cluster, nommé `photo`
(contexte `kind-photo`), héberge :

| Namespace | Contenu | Déployé par |
|---|---|---|
| `dev` | essais de développement | à la main (`kubectl apply -k k8s/overlays/dev`) |
| `test` | environnement de test | la pipeline (`scripts/deploy.sh test <tag>`) |
| `prod` | production | la pipeline, après validation (`scripts/deploy.sh prod <tag>`) |
| `ingress-nginx` | contrôleur Ingress (point d'entrée unique) | installation initiale |
| `kube-system` | metrics-server, Headlamp | installation initiale |
| `cnpg-system` | opérateur de base de données CloudNativePG | installation initiale |

Les composants de **plateforme** (`k8s/platform/`) s'installent **une seule fois** sur le cluster, à la main. Les composants de
l'**application** (`k8s/base/` et `k8s/overlays/`) sont déployés par environnement.

## 2. Prérequis

| Outil | Usage |
|---|---|
| Docker Desktop | fait tourner le nœud kind ; **au moins 6 Gio de mémoire** alloués (voir section 7) |
| `kind`, `kubectl`, `kustomize` | création du cluster, pilotage, assemblage des manifests (par exemple installés avec Homebrew) |
| `git`, `python3` | dépôt et tests (voir `05-onboarding.md`) |

Une précaution récurrente : Docker Desktop peut ramener le contexte `kubectl` sur `docker-desktop`. **Toutes les commandes de ce
dépôt précisent `--context kind-photo`** pour ne jamais viser le mauvais cluster.

## 3. Créer le cluster

```bash
kind create cluster --name photo --config kind-config.yaml
kubectl --context kind-photo get nodes
```

`kind-config.yaml` déclare un nœud de contrôle et publie les ports **80 et 443** du nœud sur la machine (`extraPortMappings`) :
c'est ce qui rend les sites joignables par `http://<nom>.localhost`.

## 4. Contrôleur Ingress

Un **seul contrôleur nginx** lit tous les Ingress du cluster : un seul point d'entrée pour l'application, la préproduction et le tableau de bord.

```bash
kubectl --context kind-photo apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl --context kind-photo wait --namespace ingress-nginx --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=120s
```

Le contrôleur écoute sur les ports 80 et 443 du nœud ; le trafic est ensuite aiguillé selon le **nom d'hôte** :

| Hôte | Service visé |
|---|---|
| `test.photo.localhost` | application de `test` (via Varnish) |
| `prod.photo.localhost` | application de `prod` (via Varnish) |
| `headlamp.localhost` | tableau de bord Headlamp |

> Le projet `ingress-nginx` a été retiré par ses mainteneurs en 2026 ; son manifest pour kind reste disponible et suffit ici. Pour la
> suite, la **Gateway API** est le successeur de l'Ingress (c'est ce qu'utilise le cluster partagé, voir section 9).

## 5. Composants de plateforme

À installer **dans cet ordre**, une seule fois :

| Composant | Commande | Vérification |
|---|---|---|
| metrics-server 0.9.0 | `kubectl --context kind-photo apply -k k8s/platform/metrics-server` | `kubectl --context kind-photo top nodes` |
| Headlamp 0.46.0 | `kubectl --context kind-photo apply -k k8s/platform/headlamp` | `curl -s -o /dev/null -w "%{http_code}\n" http://headlamp.localhost` (attendu : `200`) |
| Opérateur CloudNativePG 1.30.1 | `kubectl --context kind-photo apply --server-side -k k8s/platform/cnpg` | `kubectl --context kind-photo rollout status deployment -n cnpg-system cnpg-controller-manager` |

Points d'attention :

- **`--server-side` est obligatoire** pour l'opérateur : ses définitions de ressources dépassent la taille qu'accepte une application
  classique (erreur `metadata.annotations: Too long`).
- metrics-server reçoit l'option `--kubelet-insecure-tls` (patch dans `k8s/platform/metrics-server/kustomization.yaml`), parce que les
  kubelets de kind n'ont pas de certificat signé par l'autorité du cluster. **À ne pas faire en production.**
- Les versions sont fixées dans les fichiers (jamais `latest`) pour que l'installation soit reproductible.

Détails : `04-monitoring-scaling.md` (metrics-server, Headlamp) et `03-database.md` (opérateur).

## 6. Premier déploiement d'un environnement

```bash
./scripts/deploy.sh test local1
```

Le script construit l'image, la charge dans kind, crée le namespace et les bases, applique la migration, puis déploie l'application et le
cache (détails dans `02-ci-cd.md`). Puis :

```bash
curl -s http://test.photo.localhost/health          # ok
curl -s http://test.photo.localhost/photos          # []
```

Interface web : `http://test.photo.localhost/ui`. Le script modifie le tag d'image dans `k8s/overlays/test/kustomization.yaml` :
**ne commitez pas ce changement** (`git checkout k8s/overlays/test/kustomization.yaml`).

## 7. Ressources

Mesures (`docker stats --no-stream`, nœud kind `photo-control-plane`) :

| Situation | Mémoire utilisée |
|---|---|
| plateforme + `dev` | environ 2,5 Gio |
| plateforme + `dev` + `test` + `prod` (bases comprises) | environ 3,4 Gio |

Nœud kind sur 7,7 Gio disponibles dans cette configuration. **Recommandation : au moins 6 Gio alloués à Docker Desktop** (Settings, Resources).
Pour alléger : réduire `instances` des `Cluster` dans `test`, ou supprimer un namespace inutilisé (`kubectl delete namespace prod`).

## 8. Vérification complète

```bash
kubectl --context kind-photo get nodes                       # Ready
kubectl --context kind-photo get pods -A | grep -v Running   # ne doit lister que des pods Completed
kubectl --context kind-photo top pods -n test                # des valeurs de CPU et de mémoire
kubectl --context kind-photo get cluster -n test             # deux Cluster "healthy"
curl -s http://test.photo.localhost/health                   # ok
```

## 9. Guide de migration vers un cluster cloud

Le cluster local est un choix de commodité : les manifests décrivent **l'état voulu**, et la plupart sont portables. Le projet a été exploré
sur un **cluster managé partagé** (OVH, namespace d'équipe `team2`), ce qui permet de lister ce qui change réellement.

### 9.1 Accéder au cluster

L'accès se fait par un **kubeconfig** (certificat client), stocké hors du dépôt dans `secrets/` (dossier ignoré par Git, droits `600`).
Ce fichier contient une **clé privée** : il ne se commite jamais, ne se colle dans aucun message, et ne se met pas dans un dossier
synchronisé. On l'utilise avec `--kubeconfig` (par exemple un alias de terminal) plutôt qu'en le fusionnant dans le kubeconfig par défaut, pour ne jamais
confondre les clusters. Remarque de sécurité : la configuration fournie désactive la vérification du certificat du serveur
(`insecure-skip-tls-verify`) ; à remplacer par le certificat de l'autorité dès qu'on la possède.

Droits constatés avec `kubectl auth can-i --list -n team2` :

| Autorisé | Non autorisé |
|---|---|
| Deployments, StatefulSets, ReplicaSets, Pods et leurs journaux, Services, ConfigMaps, Secrets | Ingress, PersistentVolumeClaims, HPA, Jobs |
| HTTPRoute et GRPCRoute (Gateway API) | `pods/exec`, `port-forward`, lecture des événements |
| | tout objet de cluster (namespaces, CRD, rôles) : donc **pas d'installation d'opérateur** |

Autres constats : serveur Kubernetes 1.35, nœuds en **amd64** (la machine de développement est en arm64), Gateway API en version `v1` installée.
Découverte des types d'objets disponibles (`kubectl api-resources`) : la Gateway API est mise en œuvre par **Envoy Gateway** (types `gateway.envoyproxy.io`), **cert-manager** est installé (certificats automatiques possibles côté Gateway), et **aucun opérateur de base de données n'est présent** (pas de type `postgresql.cnpg.io`, ni autre). Le nom du `Gateway` à viser et les domaines autorisés ne sont pas lisibles avec les droits de l'équipe.

### 9.2 Ce qui change par rapport à kind

| Sujet | Sur kind (local) | Sur un cluster distant | Action |
|---|---|---|---|
| **Images** | `kind load docker-image` copie l'image dans le nœud | le cluster ne voit pas le Docker local | pousser l'image dans un **registre** (par exemple `ghcr.io`, paquet public pour éviter un secret de pull) ; remplacer le tag par `newName` + `newTag` dans l'overlay |
| **Architecture** | arm64 (Mac) | amd64 | construire pour les deux : `docker buildx build --platform linux/amd64,linux/arm64 --push ...` |
| **Entrée HTTP** | `Ingress` + contrôleur nginx (ports 80/443 du nœud) | `Gateway` géré par l'exploitant + **`HTTPRoute`** de l'équipe | remplacer `ingress.yaml` par une `HTTPRoute` (squelette ci-dessous) |
| **Stockage** | disques locaux du nœud | `StorageClass` du fournisseur | les volumes viennent des `volumeClaimTemplates`/de l'opérateur ; `PGDATA` dans un sous-dossier du volume est **indispensable** (les disques formatés contiennent `lost+found`) |
| **Base de données** | opérateur CloudNativePG, un objet `Cluster` par shard | l'opérateur exige des droits de cluster | soit l'exploitant installe l'opérateur et autorise `clusters.postgresql.cnpg.io` dans le namespace, soit repli sur des **StatefulSets** avec réplication configurée à la main |
| **Migration de schéma** | Job `photo-migrate` | pas de droit sur les Jobs | soit autoriser les Jobs, soit exécuter `migrate.py` dans un **initContainer** du Deployment |
| **Autoscaling** | HPA | pas de droit sur les HPA | demander l'autorisation, sinon scaling manuel (`replicas`) |
| **Ressources** | aucune limite stricte | quotas probables | `requests` et `limits` sur tous les pods (déjà le cas) |
| **Pipeline** | runner sur le Mac, `--context kind-photo` | l'API du cluster est joignable par Internet | `kubeconfig` stocké comme **secret GitHub Actions** ; un runner hébergé par GitHub peut suffire |

Squelette d'une `HTTPRoute` (les valeurs entre chevrons sont fournies par l'exploitant du cluster) :

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: photo-service
spec:
  parentRefs:
    - name: <nom du Gateway>
      namespace: <namespace du Gateway>
  hostnames:
    - <nom de domaine autorisé>
  rules:
    - backendRefs:
        - name: varnish
          port: 80
```

### 9.3 Plan de migration

1. Choisir un registre, construire l'image multi-architecture, la pousser, vérifier son architecture (`docker manifest inspect <image> | grep architecture`).
2. Créer un overlay `k8s/overlays/ovh/` (namespace d'équipe, image du registre, `HTTPRoute` au lieu de l'Ingress, sans HPA).
3. Régler la base de données et la migration selon les droits obtenus (voir tableau).
4. Déployer en lecture seule d'abord (`kubectl apply --dry-run=server`), puis réellement, et valider avec un pod ponctuel
   (`kubectl run tmp-curl --image=curlimages/curl ...`) puisque `exec` et `port-forward` sont interdits.
5. Garder les identifiants (kubeconfig, mots de passe) hors du dépôt.

### 9.4 État de la migration

| Étape | État |
|---|---|
| Accès au cluster, droits relevés | fait |
| Questions posées à l'exploitant (opérateur, Jobs, Gateway et domaines, HPA, stockage et quotas, registre) | envoyées ; **réponses à reporter ici** |
| Image multi-architecture dans un registre | à faire |
| Overlay `ovh` | à faire |
| Déploiement et validation | à faire |

## 10. Dépannage

| Symptôme | Cause probable | Remède |
|---|---|---|
| une commande agit sur le mauvais cluster | contexte `docker-desktop` actif | toujours `--context kind-photo` |
| `Too long` en installant l'opérateur | application classique | ajouter `--server-side` |
| `no matches for kind "Cluster"` | l'opérateur n'est pas installé | installer l'opérateur (section 5) avant d'appliquer un overlay |
| `503` juste après un déploiement | pods Varnish ou application pas encore prêts | attendre, relancer ; `kubectl rollout status` |
| pods `Pending` ou nœud saturé | mémoire Docker insuffisante | augmenter la mémoire de Docker Desktop, supprimer un namespace |
| `-n ""` ou namespace `default` visé | variable d'environnement vide | écrire le namespace en toutes lettres, ou `${1:?}` dans un script |
