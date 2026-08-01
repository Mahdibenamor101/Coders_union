# Phase 4 — Dashboard

Dashboard Next.js 14 (`frontend/`) : tout le parcours caméra → alerte → revue
humaine se fait dans le navigateur.

## Pages

| Route | Contenu |
|---|---|
| `/login` | Connexion par clé API (comptes/JWT en Phase 5) |
| `/` | Vue live : alertes à vérifier, flux temps réel (WebSocket), état des caméras |
| `/alerts` | Incidents avec miniatures, filtres statut/règle |
| `/alerts/[id]` | Player vidéo du clip, indices du moteur de règles, revue (confirmer / faux positif / ignorer) |
| `/cameras` | Liste + création organisation → magasin → caméra |
| `/cameras/[id]` | Éditeur visuel de zones sur snapshot caméra + réglage des seuils par caméra |
| `/stats` | Alertes par jour et **taux de faux positifs par règle** (le guide de réglage des seuils) |

## Ajouts backend

- `WS /ws/alerts?api_key=…` : relaie le canal Redis `alerts_feed` (clé invalide →
  fermeture 4401). CORS configurable (`CORS_ORIGINS`).
- `GET /stats/alerts-per-day?days=` et `GET /stats/rules` (volumes par statut de
  revue + taux de FP = faux positifs / alertes revues).
- `GET /cameras/{id}/snapshot-url` : le worker publie `{camera_id}/snapshot.jpg`
  toutes les 10 s ; sert de fond à l'éditeur de zones.

## Lancer

```bash
docker compose up -d --build          # inclut le service frontend (port 3000)
# ou en dev : cd frontend && npm install && npm run dev
```

Ouvrir http://localhost:3000 et se connecter avec la valeur de `API_KEY`.

## Parcours de validation (critère de fin de phase)

1. **Login** avec la clé API.
2. **Caméras** → créer organisation, magasin, puis caméra
   (`rtsp://mediamtx:8554/teststream` pour le flux de test). Seule étape hors
   navigateur : recopier l'ID affiché dans `WORKER_CAMERA_ID` (`.env`) et
   `docker compose up -d worker` — la supervision multi-caméras lèvera cette
   étape.
3. **Caméra** → dessiner les zones (rayon, caisse, sortie) sur le snapshot,
   ajuster les seuils : appliqués au worker en direct.
4. **Vue live** : les alertes apparaissent en temps réel (WebSocket).
5. **Alerte** → regarder le clip, vérifier les indices, décider :
   confirmer / faux positif / ignorer.
6. **Statistiques** : suivre le taux de faux positifs par règle et resserrer
   les seuils des caméras concernées.

Ce parcours complet (hors variable d'environnement du worker) a été validé par
un test navigateur automatisé (Playwright) : login → création via UI → alerte
poussée par WebSocket → revue « faux positif » → taux de FP à 100 % dans les
stats.

## Vérifications automatisées

- `cd backend && .venv/bin/pytest` — 35 tests (stats inclus).
- `cd frontend && npm run build` — build + ESLint.
- WebSocket vérifié contre un serveur réel (rejet 4401, relais `alerts_feed`).

## Limites assumées

- Auth par clé API partagée ; comptes, rôles et invitations en Phase 5.
- Les miniatures chargent une URL présignée par alerte (une requête chacune) —
  optimisable si besoin.
- L'éditeur de zones ne permet pas de modifier un polygone existant
  (supprimer/redessiner).
