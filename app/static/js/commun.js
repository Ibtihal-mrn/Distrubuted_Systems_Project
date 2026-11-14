// Fonctions partagées par toutes les pages. Les autres fichiers les importent avec "import".

export const $ = (id) => document.getElementById(id);

// Crée un élément HTML. Les textes sont ajoutés comme TEXTE (jamais interprétés
// comme du HTML) : un nom de fichier malveillant ne peut rien injecter.
export function el(balise, proprietes = {}, ...enfants) {
  const e = document.createElement(balise);
  for (const [cle, valeur] of Object.entries(proprietes)) {
    if (cle === "class") e.className = valeur;
    else if (cle.startsWith("on")) e.addEventListener(cle.slice(2), valeur);
    else if (typeof valeur === "boolean") { if (valeur) e.setAttribute(cle, ""); }
    else e.setAttribute(cle, valeur);
  }
  for (const enfant of enfants) e.append(enfant);   // une chaîne devient un nœud texte
  return e;
}

export function taille(octets) {
  if (octets < 1024) return octets + " o";
  if (octets < 1024 * 1024) return (octets / 1024).toFixed(0) + " Ko";
  return (octets / 1024 / 1024).toFixed(1).replace(".", ",") + " Mo";
}

// Affiche un message dans un élément ; etat : "" (neutre), "ok" ou "ko".
export function message(element, texte, etat = "") {
  element.textContent = texte;
  element.className = "msg " + etat;
}

// Appel HTTP. Si le serveur répond 401 (non connecté), on retourne à la page de connexion.
export async function api(url, options = {}) {
  const reponse = await fetch(url, options);
  if (reponse.status === 401 && url !== "/login" && url !== "/register") {
    location.href = "/";
    throw new Error("connexion requise");
  }
  return reponse;
}

export function envoyerJson(url, methode, corps) {
  return api(url, { method: methode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
}

export async function texteErreur(reponse) {
  try { return (await reponse.json()).erreur || "erreur " + reponse.status; }
  catch { return "erreur " + reponse.status; }
}

// La redirection vers "/" est déjà lancée quand cette erreur est levée : on évite
// seulement qu'elle s'affiche dans la console. Les autres erreurs restent visibles.
window.addEventListener("unhandledrejection", (e) => {
  if (e.reason && e.reason.message === "connexion requise") e.preventDefault();
});

// À appeler au début de chaque page protégée : vérifie la connexion (sinon retour à "/"),
// construit l'en-tête commun et renvoie l'utilisateur. "page" = "galerie" ou "albums".
export async function exigerConnexion(page) {
  const reponse = await fetch("/me");
  if (!reponse.ok) {
    location.href = "/";
    throw new Error("connexion requise");
  }
  const utilisateur = await reponse.json();

  const lien = (adresse, texte, actif) => el("a", { href: adresse, class: actif ? "actif" : "" }, texte);
  $("entete").replaceChildren(
    el("div", { class: "ligne" },
      el("a", { class: "marque", href: "/galerie" }, "Photos"),
      el("nav", { class: "nav", "aria-label": "Navigation principale" },
        lien("/galerie", "Mes photos", page === "galerie"),
        lien("/mes-albums", "Albums", page === "albums"))),
    el("div", { class: "ligne" },
      el("span", { class: "utilisateur" }, utilisateur.email),
      el("button", { class: "bouton discret", onclick: async () => {
        await fetch("/logout", { method: "POST" });
        location.href = "/";
      } }, "Se déconnecter")));
  return utilisateur;
}

// ---------- Visionneuse : photo en grand, avec flèches pour passer à la suivante ----------

let visionneuse = null;      // la fenêtre <dialog>, créée au premier usage
let liste = [];              // photos parcourues par les flèches
let position = 0;            // indice de la photo affichée
const vue = {};              // éléments de la visionneuse (image, légende, flèches)

function aller(decalage) {
  // Modulo : après la dernière photo on revient à la première, et inversement.
  position = (position + decalage + liste.length) % liste.length;
  afficherPosition();
}

function afficherPosition() {
  const photo = liste[position];
  vue.image.src = "/photos/" + photo.id;
  vue.image.alt = photo.nom;
  vue.legende.textContent = photo.nom + "  (" + (position + 1) + " sur " + liste.length + ")";
  vue.precedent.hidden = vue.suivant.hidden = liste.length < 2;   // pas de flèches pour une seule photo
}

function creerVisionneuse() {
  vue.image = el("img", { alt: "" });
  vue.legende = el("p");
  vue.precedent = el("button", { class: "fleche gauche", "aria-label": "Photo précédente", onclick: () => aller(-1) }, "‹");
  vue.suivant = el("button", { class: "fleche droite", "aria-label": "Photo suivante", onclick: () => aller(1) }, "›");
  const fermer = el("button", { class: "fermer-visionneuse", "aria-label": "Fermer", onclick: () => visionneuse.close() }, "×");

  visionneuse = el("dialog", { class: "visionneuse", "aria-label": "Visionneuse de photos" },
    vue.image, vue.legende, vue.precedent, vue.suivant, fermer);

  // Un clic à côté de la photo (sur le fond sombre) ferme la fenêtre ; Échap aussi.
  visionneuse.addEventListener("click", (e) => { if (e.target === visionneuse) visionneuse.close(); });
  // Flèches du clavier
  visionneuse.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" && liste.length > 1) aller(-1);
    if (e.key === "ArrowRight" && liste.length > 1) aller(1);
  });
  // Glissement du doigt sur écran tactile
  let departX = null;
  visionneuse.addEventListener("touchstart", (e) => { departX = e.touches[0].clientX; }, { passive: true });
  visionneuse.addEventListener("touchend", (e) => {
    if (departX === null || liste.length < 2) return;
    const ecart = e.changedTouches[0].clientX - departX;
    if (Math.abs(ecart) > 50) aller(ecart < 0 ? 1 : -1);   // vers la gauche : photo suivante
    departX = null;
  });
  document.body.append(visionneuse);
}

function ouvrirVisionneuse(photos, indice) {
  if (!visionneuse) creerVisionneuse();
  liste = photos;
  position = indice;
  afficherPosition();
  visionneuse.showModal();
}

// ---------- Grille de photos ----------

// Dessine une grille de photos dans "conteneur". Options (toutes facultatives) :
//   selection, surSelection : Set d'identifiants cochés, et fonction appelée à chaque changement
//   modeSelection           : true = les cases rondes sont affichées et un clic sur une photo la coche
//                             (sinon, un clic sur une photo l'ouvre en grand)
//   surSupprimer(photo)     : affiche une croix "Supprimer" dans le coin de la photo
//   surRetirer(photo)       : affiche une croix "Retirer de l'album" dans le coin de la photo
export function dessinerGrille(conteneur, photos, options = {}) {
  conteneur.replaceChildren();
  conteneur.classList.toggle("selection", Boolean(options.modeSelection));

  photos.forEach((photo, indice) => {
    const apercu = el("img", { src: "/photos/" + photo.id, alt: photo.nom, loading: "lazy" });
    // Format non affichable par le navigateur (ex. HEIC) : on remplace l'image par un texte.
    apercu.addEventListener("error", () => apercu.replaceWith(el("div", { class: "apercu-absent" }, "Aperçu indisponible")));

    const carte = el("figure", { class: "epreuve" });
    let caseACocher = null;

    if (options.modeSelection && options.selection) {
      caseACocher = el("input", { type: "checkbox", "aria-label": "Sélectionner " + photo.nom });
      caseACocher.checked = options.selection.has(photo.id);
      carte.classList.toggle("cochee", caseACocher.checked);
      caseACocher.addEventListener("change", () => {
        if (caseACocher.checked) options.selection.add(photo.id); else options.selection.delete(photo.id);
        carte.classList.toggle("cochee", caseACocher.checked);
        if (options.surSelection) options.surSelection();
      });
      carte.append(el("label", { class: "coche" }, caseACocher, el("span")));
    }

    // Croix dans le coin de la photo : supprime (galerie) ou retire de l'album (page album).
    // Elle disparaît en mode sélection.
    if (!options.modeSelection && options.surSupprimer) {
      carte.append(el("button", { class: "coin", title: "Supprimer", "aria-label": "Supprimer " + photo.nom,
                                  onclick: () => options.surSupprimer(photo) }, "×"));
    } else if (!options.modeSelection && options.surRetirer) {
      carte.append(el("button", { class: "coin", title: "Retirer de l'album", "aria-label": "Retirer " + photo.nom + " de l'album",
                                  onclick: () => options.surRetirer(photo) }, "×"));
    }

    // Clic sur la photo : en mode sélection on la coche, sinon on l'ouvre en grand.
    const surClic = caseACocher ? () => caseACocher.click() : () => ouvrirVisionneuse(photos, indice);
    carte.append(
      el("button", { class: "apercu-bouton", "aria-label": (caseACocher ? "Sélectionner " : "Agrandir ") + photo.nom, onclick: surClic }, apercu),
      el("figcaption", { class: "legende" },
        el("span", { class: "nom", title: photo.nom }, photo.nom),
        el("div", { class: "ligne-legende" },
          el("span", { class: "meta" }, taille(photo.taille)),
          el("span", { class: "puce" }, "shard " + photo.shard))));
    conteneur.append(carte);
  });
}
