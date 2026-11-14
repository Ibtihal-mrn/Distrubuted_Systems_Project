import { $, el, message, api, envoyerJson, texteErreur, exigerConnexion } from "./commun.js";

await exigerConnexion("albums");

// Couverture d'un album : un dégradé bleu dont la teinte vient de l'identifiant,
// donc un album garde toujours la même couverture.
function degrade(id) {
  const n = parseInt(id.slice(0, 6), 16);
  const teinte = 200 + (n % 30), angle = 120 + (n % 90);
  return "linear-gradient(" + angle + "deg, hsl(" + teinte + " 55% 32%), hsl(" + (teinte + 10) + " 60% 66%))";
}

async function chargerAlbums() {
  const albums = await (await api("/albums")).json();
  $("albums").replaceChildren(...albums.map((a) =>
    // Toute la tuile est un lien vers la page de détail ; l'identifiant passe dans l'adresse (?id=...)
    el("a", { class: "epreuve tuile", href: "/album?id=" + a.id },
      el("div", { class: "couverture", style: "background:" + degrade(a.id) }),
      el("div", { class: "legende" },
        el("span", { class: "nom", title: a.nom }, a.nom),
        el("div", { class: "ligne-legende" },
          el("span", { class: "badge" + (a.partage ? " partage" : "") }, a.partage ? "Partagé" : "Privé"),
          el("span", { class: "meta" }, a.est_proprietaire ? "Créé par vous" : "Partagé avec vous"))))));
  $("vide-albums").hidden = albums.length > 0;
}

$("form-album").addEventListener("submit", async (e) => {
  e.preventDefault();
  const reponse = await envoyerJson("/albums", "POST", { nom: $("nom-album").value, partage: $("album-partage").checked });
  if (!reponse.ok) { message($("msg-albums"), await texteErreur(reponse), "ko"); return; }
  message($("msg-albums"), "Album créé", "ok");
  $("form-album").reset();
  chargerAlbums();
});

chargerAlbums();
