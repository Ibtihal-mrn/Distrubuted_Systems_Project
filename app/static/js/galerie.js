import { $, el, taille, message, api, envoyerJson, texteErreur, dessinerGrille, exigerConnexion } from "./commun.js";

await exigerConnexion("galerie");   // retour à "/" si non connecté

let photos = [];               // photos affichées
let modeSelection = false;     // true : les cases rondes sont visibles
const selection = new Set();   // identifiants des photos cochées

// ---------- Affichage ----------

function dessiner() {
  dessinerGrille($("grille"), photos, { selection, modeSelection, surSelection: majBarre, surSupprimer: supprimerPhoto });
  $("vide-photos").hidden = photos.length > 0;
  majBarre();
}

// La barre flottante n'apparaît que s'il y a une sélection.
function majBarre() {
  const n = selection.size;
  $("barre-selection").hidden = n === 0;
  $("compte-selection").textContent = n + (n > 1 ? " photos sélectionnées" : " photo sélectionnée");
  $("btn-comparer").disabled = n !== 2;   // on compare exactement deux photos
  $("btn-ranger").disabled = n === 0 || !$("choix-album").value;
}

async function chargerPhotos() {
  photos = await (await api("/photos")).json();
  selection.clear();
  $("resultat").hidden = true;
  dessiner();
}

async function chargerAlbums() {
  const albums = await (await api("/albums")).json();
  $("choix-album").replaceChildren(el("option", { value: "" }, "Choisir un album"),
    ...albums.map((a) => el("option", { value: a.id }, a.nom)));
  majBarre();
}

// Affiche un résultat de comparaison dans le panneau, avec un bouton pour le fermer.
function montrerResultat(...contenu) {
  $("resultat").replaceChildren(el("div", {}, ...contenu),
    el("button", { class: "bouton discret petit", onclick: () => { $("resultat").hidden = true; } }, "Fermer"));
  $("resultat").hidden = false;
}

// ---------- Mode sélection ----------

$("btn-selectionner").addEventListener("click", () => {
  modeSelection = !modeSelection;
  selection.clear();   // en quittant le mode, on oublie la sélection
  $("btn-selectionner").textContent = modeSelection ? "Terminer la sélection" : "Sélectionner";
  $("btn-selectionner").setAttribute("aria-pressed", String(modeSelection));
  dessiner();
});

$("btn-annuler").addEventListener("click", () => { selection.clear(); dessiner(); });

// ---------- Envoi (bouton, ou glisser-déposer) ----------

async function envoyer(fichiers) {
  if (fichiers.length === 0) return;
  message($("msg-envoi"), "Envoi de " + fichiers.length + " fichier(s)…");
  let reussies = 0, doublons = 0;
  const erreurs = [];
  for (const fichier of fichiers) {
    const formulaire = new FormData();
    formulaire.append("photo", fichier);   // champ attendu par le serveur
    const reponse = await api("/photos", { method: "POST", body: formulaire });
    if (reponse.ok) { reussies++; if ((await reponse.json()).avertissement) doublons++; }
    else erreurs.push(fichier.name + " : " + await texteErreur(reponse));
  }
  let texte = reussies + " photo(s) envoyée(s)";
  if (doublons) texte += ", dont " + doublons + " identique(s) à une photo déjà présente";
  if (erreurs.length) texte += ". Échecs : " + erreurs.join(" ; ");
  message($("msg-envoi"), texte, erreurs.length ? "ko" : "ok");
  $("fichiers").value = "";
  await chargerPhotos();
  if (!$("doublons").hidden) afficherDoublons();   // le panneau des doublons reste à jour
}

$("fichiers").addEventListener("change", () => envoyer(Array.from($("fichiers").files)));

const depot = $("depot");
for (const evenement of ["dragenter", "dragover"]) {
  depot.addEventListener(evenement, (e) => { e.preventDefault(); depot.classList.add("survol"); });
}
for (const evenement of ["dragleave", "drop"]) {
  depot.addEventListener(evenement, (e) => { e.preventDefault(); depot.classList.remove("survol"); });
}
depot.addEventListener("drop", (e) => envoyer(Array.from(e.dataTransfer.files)));

// ---------- Suppression, comparaison, rangement ----------

async function supprimerPhoto(photo) {
  if (!confirm("Supprimer « " + photo.nom + " » ?")) return;
  const reponse = await api("/photos/" + photo.id, { method: "DELETE" });
  if (!reponse.ok) { message($("msg-envoi"), await texteErreur(reponse), "ko"); return; }
  await chargerPhotos();
  if (!$("doublons").hidden) afficherDoublons();
}

$("btn-comparer").addEventListener("click", async () => {
  const [a, b] = Array.from(selection);
  const reponse = await api("/compare?a=" + a + "&b=" + b);
  if (!reponse.ok) { message($("msg-envoi"), await texteErreur(reponse), "ko"); return; }
  const d = await reponse.json();
  montrerResultat(
    el("strong", {}, d.identiques ? "Photos identiques (même contenu)" : "Photos différentes"),
    el("p", { class: "muted" }, d.a.nom + " et " + d.b.nom + ". Même type : " + (d.meme_type ? "oui" : "non")
                                + ". Écart de taille : " + taille(d.difference_taille) + "."));
});

$("choix-album").addEventListener("change", majBarre);

$("btn-ranger").addEventListener("click", async () => {
  const albumId = $("choix-album").value;
  let rangees = 0;
  for (const photoId of selection) {
    const reponse = await envoyerJson("/albums/" + albumId + "/photos", "POST", { photo_id: photoId });
    if (reponse.ok) rangees++;
  }
  message($("msg-envoi"), rangees + " photo(s) rangée(s) dans l'album", "ok");
  selection.clear();
  dessiner();
});

// ---------- Doublons : affichage à la demande, puis suppression des copies ----------

// Affiche chaque groupe de photos identiques ; la plus ancienne est conservée (le serveur les trie par date).
async function afficherDoublons() {
  const groupes = await (await api("/duplicates")).json();
  const panneau = $("doublons");

  if (groupes.length === 0) {
    panneau.replaceChildren(el("p", { class: "muted" }, "Aucune photo en double."));
    panneau.hidden = false;
    return;
  }

  const nbCopies = groupes.reduce((total, g) => total + g.photos.length - 1, 0);
  const entete = el("div", { class: "entete-doublons" },
    el("div", {},
      el("strong", {}, groupes.length + " groupe(s) de photos identiques"),
      el("p", { class: "muted" }, "Dans chaque groupe, la plus ancienne est conservée.")),
    el("button", { class: "bouton danger", onclick: () => supprimerCopies(groupes) },
       "Supprimer les " + nbCopies + " copie(s)"));

  const lignes = groupes.map((g) => el("div", { class: "groupe-doublons" },
    el("div", { class: "vignettes" }, ...g.photos.map((p, i) =>
      el("figure", { class: "vignette" },
        el("img", { src: "/photos/" + p.id, alt: p.nom, loading: "lazy" }),
        el("figcaption", {}, i === 0 ? "Conservée" : "Copie")))),
    el("div", { class: "infos-groupe" },
      el("span", { class: "muted" }, g.photos.map((p) => p.nom).join(", ") + " (" + taille(g.taille) + " chacune)"),
      el("button", { class: "bouton secondaire petit", onclick: () => supprimerCopies([g]) }, "Supprimer les copies de ce groupe"))));

  panneau.replaceChildren(entete, ...lignes);
  panneau.hidden = false;
}

// Supprime, dans chaque groupe donné, toutes les photos sauf la première (la plus ancienne).
async function supprimerCopies(groupes) {
  const aSupprimer = groupes.flatMap((g) => g.photos.slice(1));
  if (!confirm("Supprimer définitivement " + aSupprimer.length + " copie(s) ? La plus ancienne de chaque groupe est conservée.")) return;
  let supprimees = 0;
  for (const photo of aSupprimer) {
    const reponse = await api("/photos/" + photo.id, { method: "DELETE" });
    if (reponse.ok) supprimees++;
  }
  message($("msg-envoi"), supprimees + " copie(s) supprimée(s)", supprimees === aSupprimer.length ? "ok" : "ko");
  await chargerPhotos();
  afficherDoublons();
}

$("btn-doublons").addEventListener("click", () => {
  const ouvert = !$("doublons").hidden;
  if (ouvert) {   // deuxième clic : on masque le panneau
    $("doublons").hidden = true;
    $("btn-doublons").textContent = "Afficher les doublons";
    $("btn-doublons").setAttribute("aria-expanded", "false");
  } else {
    $("btn-doublons").textContent = "Masquer les doublons";
    $("btn-doublons").setAttribute("aria-expanded", "true");
    afficherDoublons();
  }
});

chargerPhotos();
chargerAlbums();
