import { $, el, message, api, envoyerJson, texteErreur, dessinerGrille, exigerConnexion } from "./commun.js";

await exigerConnexion("albums");

// L'identifiant de l'album est dans l'adresse : /album?id=...
const id = new URLSearchParams(location.search).get("id");
if (!id) location.href = "/mes-albums";

let photosAlbum = [];            // photos actuellement dans l'album
let membres = [];                // membres (visible du propriétaire seulement)
const selectionAjout = new Set();   // photos cochées dans la fenêtre d'ajout

// ---------- Affichage de l'album ----------

async function chargerAlbum() {
  const reponse = await api("/albums/" + id);
  if (!reponse.ok) { message($("msg-album"), await texteErreur(reponse), "ko"); return; }
  const donnees = await reponse.json();
  const album = donnees.album;
  photosAlbum = donnees.photos;
  membres = donnees.membres;

  $("titre-album").textContent = album.nom;
  $("badge-album").textContent = album.partage ? "Partagé" : "Privé";
  $("badge-album").className = "badge" + (album.partage ? " partage" : "");

  // Seul le propriétaire voit les paramètres et peut retirer des photos.
  $("gestion").hidden = !album.est_proprietaire;
  if (album.est_proprietaire) {
    $("nom-album").value = album.nom;
    $("album-partage").checked = album.partage;
    $("bloc-membres").hidden = !album.partage;   // les membres n'existent que pour un album partagé
    dessinerMembres();
  }

  dessinerGrille($("grille"), photosAlbum, album.est_proprietaire ? { surRetirer: retirerPhoto } : {});
  $("vide-album").hidden = photosAlbum.length > 0;
}

async function retirerPhoto(photo) {
  const reponse = await api("/albums/" + id + "/photos/" + photo.id, { method: "DELETE" });
  if (reponse.ok) chargerAlbum(); else message($("msg-album"), await texteErreur(reponse), "ko");
}

// ---------- Paramètres : nom, partage, membres ----------

$("form-parametres").addEventListener("submit", async (e) => {
  e.preventDefault();
  const partage = $("album-partage").checked;
  // Passer en privé retire tous les membres : on demande confirmation s'il y en a.
  if (!partage && membres.length > 0 &&
      !confirm("Passer l'album en privé retire ses " + membres.length + " membre(s). Continuer ?")) {
    $("album-partage").checked = true;
    return;
  }
  const reponse = await envoyerJson("/albums/" + id, "PATCH", { nom: $("nom-album").value, partage });
  if (!reponse.ok) { message($("msg-album"), await texteErreur(reponse), "ko"); return; }
  message($("msg-album"), "Paramètres enregistrés", "ok");
  chargerAlbum();
});

// Un changement du curseur « Partagé » montre ou cache aussitôt la section des membres.
$("album-partage").addEventListener("change", () => { $("bloc-membres").hidden = !$("album-partage").checked; });

function dessinerMembres() {
  $("liste-membres").replaceChildren(...membres.map((m) =>
    el("li", { class: "membre" },
      el("span", {}, m.email),
      el("button", { class: "bouton discret petit", onclick: () => retirerMembre(m) }, "Retirer"))));
  $("aucun-membre").hidden = membres.length > 0;
}

async function retirerMembre(membre) {
  const reponse = await api("/albums/" + id + "/membres/" + membre.id, { method: "DELETE" });
  if (reponse.ok) chargerAlbum(); else message($("msg-album"), await texteErreur(reponse), "ko");
}

$("form-membre").addEventListener("submit", async (e) => {
  e.preventDefault();
  const reponse = await envoyerJson("/albums/" + id + "/membres", "POST", { email: $("email-membre").value });
  if (reponse.ok) { message($("msg-album"), "Membre ajouté", "ok"); $("form-membre").reset(); chargerAlbum(); }
  else message($("msg-album"), await texteErreur(reponse), "ko");
});

$("btn-supprimer-album").addEventListener("click", async () => {
  if (!confirm("Supprimer cet album ? Les photos ne sont pas supprimées.")) return;
  const reponse = await api("/albums/" + id, { method: "DELETE" });
  if (reponse.ok) location.href = "/mes-albums";
  else message($("msg-album"), await texteErreur(reponse), "ko");
});

// ---------- Ajout de photos : fenêtre avec envoi de fichiers ou choix parmi mes photos ----------

function majAjout() {
  const n = selectionAjout.size;
  $("btn-valider-ajout").disabled = n === 0;
  $("btn-valider-ajout").textContent = n === 0 ? "Ajouter" : "Ajouter " + n + " photo" + (n > 1 ? "s" : "");
}

// Affiche mes photos qui ne sont pas encore dans l'album, avec des cases à cocher.
async function chargerChoix() {
  const mesPhotos = await (await api("/photos")).json();
  const dejaDedans = new Set(photosAlbum.map((p) => p.id));
  const disponibles = mesPhotos.filter((p) => !dejaDedans.has(p.id));
  selectionAjout.clear();
  dessinerGrille($("grille-ajout"), disponibles, { selection: selectionAjout, modeSelection: true, surSelection: majAjout });
  $("vide-ajout").hidden = disponibles.length > 0;
  majAjout();
}

$("btn-ajouter").addEventListener("click", async () => {
  message($("msg-ajout"), "");
  await chargerChoix();
  $("ajout").showModal();
});
$("btn-fermer-ajout").addEventListener("click", () => $("ajout").close());

// Range les photos cochées dans l'album.
$("btn-valider-ajout").addEventListener("click", async () => {
  let ajoutees = 0;
  for (const photoId of selectionAjout) {
    const reponse = await envoyerJson("/albums/" + id + "/photos", "POST", { photo_id: photoId });
    if (reponse.ok) ajoutees++;
  }
  $("ajout").close();
  message($("msg-album"), ajoutees + " photo(s) ajoutée(s) à l'album", "ok");
  chargerAlbum();
});

// Envoie de nouvelles photos puis les range directement dans l'album.
async function envoyerDansAlbum(fichiers) {
  if (fichiers.length === 0) return;
  message($("msg-ajout"), "Envoi de " + fichiers.length + " fichier(s)…");
  let ajoutees = 0;
  const erreurs = [];
  for (const fichier of fichiers) {
    const formulaire = new FormData();
    formulaire.append("photo", fichier);
    const envoi = await api("/photos", { method: "POST", body: formulaire });
    if (!envoi.ok) { erreurs.push(fichier.name + " : " + await texteErreur(envoi)); continue; }
    const photo = await envoi.json();
    const rangement = await envoyerJson("/albums/" + id + "/photos", "POST", { photo_id: photo.id });
    if (rangement.ok) ajoutees++; else erreurs.push(fichier.name + " : " + await texteErreur(rangement));
  }
  let texte = ajoutees + " photo(s) envoyée(s) et ajoutée(s) à l'album";
  if (erreurs.length) texte += ". Échecs : " + erreurs.join(" ; ");
  message($("msg-ajout"), texte, erreurs.length ? "ko" : "ok");
  $("fichiers-album").value = "";
  await chargerAlbum();
  await chargerChoix();
}

$("fichiers-album").addEventListener("change", () => envoyerDansAlbum(Array.from($("fichiers-album").files)));
const depotAlbum = $("depot-album");
for (const evenement of ["dragenter", "dragover"]) {
  depotAlbum.addEventListener(evenement, (e) => { e.preventDefault(); depotAlbum.classList.add("survol"); });
}
for (const evenement of ["dragleave", "drop"]) {
  depotAlbum.addEventListener(evenement, (e) => { e.preventDefault(); depotAlbum.classList.remove("survol"); });
}
depotAlbum.addEventListener("drop", (e) => envoyerDansAlbum(Array.from(e.dataTransfer.files)));

chargerAlbum();
