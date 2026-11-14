import { $, message, envoyerJson, texteErreur } from "./commun.js";

// Déjà connecté (cookie valide) ? On va directement à la galerie.
const moi = await fetch("/me");
if (moi.ok) location.href = "/galerie";

// Mode actuel du formulaire : false = connexion, true = création de compte.
let inscription = false;

// Met à jour les textes de la page selon le mode.
function afficherMode() {
  $("titre-formulaire").textContent = inscription ? "Créer un compte" : "Connexion";
  $("btn-principal").textContent = inscription ? "Créer mon compte" : "Se connecter";
  $("btn-basculer").textContent = inscription ? "J'ai déjà un compte" : "Créer un compte";
  // Indique au navigateur s'il doit proposer un mot de passe existant ou en suggérer un nouveau.
  $("mdp").setAttribute("autocomplete", inscription ? "new-password" : "current-password");
  message($("msg-connexion"), "");   // efface l'ancien message d'erreur
}

// Envoie email + mot de passe à /login ou /register ; en cas de succès, le serveur a posé le cookie.
async function authentifier(chemin) {
  const reponse = await envoyerJson(chemin, "POST", { email: $("email").value, mot_de_passe: $("mdp").value });
  if (!reponse.ok) { message($("msg-connexion"), await texteErreur(reponse), "ko"); return; }
  location.href = "/galerie";
}

// Le bouton principal fait l'action du mode actuel.
$("form-connexion").addEventListener("submit", (e) => {
  e.preventDefault();
  authentifier(inscription ? "/register" : "/login");
});

// Le bouton secondaire change de mode.
$("btn-basculer").addEventListener("click", () => {
  inscription = !inscription;
  afficherMode();
});