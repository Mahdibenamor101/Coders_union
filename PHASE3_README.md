# Phase 3 — Moteur de comportements

Le worker combine désormais les signaux (zones, objets, pose) dans un moteur de
règles qui produit des **alertes de comportement à vérifier** — jamais un
verdict. Chaque alerte embarque un score, les indices qui l'expliquent, un clip
(20 s avant / 20 s après) et une thumbnail, et attend une revue humaine.

## Les 5 règles (SPEC §6, dans l'ordre)

| # | Règle | Signaux | Score | Sévérité |
|---|---|---|---|---|
| 1 | `dissimulation` | objet saisi (main/pose) 15 → objet non visible 35 → sortie du rayon 30 | jusqu'à 80 | high |
| 2 | `passage_sans_caisse` | entrée en zone `sortie` avec ≥ 10 s en rayon et < 5 s en caisse | 65 | medium |
| 3 | `temps_anormal` | `person_dwell` en zone sensible avec rayon de déplacement ≤ 0.05 | 40 | low |
| 4 | gestes d'observation | alternances de tête marquées — **bonus uniquement**, jamais seul | +15 | — |
| 5 | `zone_interdite` | entrée en zone `reserve` | 70 | high |

Fonctionnement : chaque indice (« finding ») est horodaté et expire après
`window_seconds` (120 s). Une alerte part quand la somme des indices d'une même
personne trackée atteint `alert_threshold` (60), puis un cooldown (60 s) et une
remise à zéro évitent le spam. Tous les seuils sont réglables **par caméra** :

```bash
curl -X PUT http://localhost:8000/cameras/$CAMERA/settings \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"alert_threshold": 50, "dwell_seconds": 20}'
# Appliqué à chaud par le worker (commande Redis update_settings).
```

## Chaîne d'une alerte

```
perception (YOLO pose + objets) ─▶ événements ─▶ moteur de règles
                                                      │ décision
      buffer circulaire ──▶ clip .mp4 + thumbnail .jpg ─▶ MinIO
                                                      │ behavior_alert (Redis)
                               API ──▶ table alerts (statut pending) ──▶ canal alerts_feed
```

- `GET /alerts?status=&rule=&camera_id=` — liste, filtres (base des stats de
  faux positifs par règle de la Phase 4).
- `POST /alerts/{id}/review` — `confirmed | false_positive | dismissed`
  (+ `reviewed_by`), ou retour à `pending`.
- `GET /alerts/{id}/clip-url` / `thumbnail-url` — URLs présignées.

## Tests automatisés (critère de fin de phase)

```bash
cd worker && ../backend/.venv/bin/pytest -v tests/test_scenarios.py
```

`test_scenarios.py` rejoue la chaîne complète perception → zones → règles avec
des détections synthétiques :
- **scénario dissimulation** (saisie → disparition → sortie du rayon) → 1 alerte
  `dissimulation` high avec les indices `grab` et `conceal` ;
- **shopping normal** (objet toujours visible, passage caisse, sortie) → 0 alerte ;
- **flânerie sans saisie** → 0 alerte.

Couverture du moteur (exigence SPEC §8 : ≥ 80 %) :

```bash
cd worker && ../backend/.venv/bin/pytest --cov=worker.rules_engine --cov=worker.perception
# rules_engine.py : 99 % — perception.py : 95 %
```

Suites complètes : `cd backend && .venv/bin/pytest` (32 tests) et
`cd worker && ../backend/.venv/bin/pytest` (55 tests).

## Test manuel sur flux vidéo

1. Stack et zones en place (PHASE1/PHASE2_README), avec au moins une zone
   `rayon` et une zone `sortie` (et idéalement `caisse`).
2. Diffuser une vidéo libre de droits avec des personnes :
   `./scripts/stream_video.sh video.mp4`.
3. Suivre les décisions : `docker compose logs -f worker`
   (`alert decision rule=… score=…`), puis :

```bash
curl -s "http://localhost:8000/alerts" -H "X-API-Key: $KEY"
curl -s "http://localhost:8000/alerts/$ALERT/clip-url" -H "X-API-Key: $KEY"
curl -s -X POST "http://localhost:8000/alerts/$ALERT/review" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"status": "false_positive", "reviewed_by": "test"}'
```

La règle la plus simple à déclencher sur une vidéo quelconque est
`passage_sans_caisse` : dessiner un `rayon` là où les gens marchent puis une
`sortie` sur leur trajectoire.

## Limites assumées

- La perception (association objet↔main, dissimulation, gestes) repose sur des
  heuristiques simples : c'est le rôle des seuils par caméra et des stats de
  faux positifs (Phase 4) de l'ajuster. L'étape optionnelle « API vision
  multimodale pour lever l'ambiguïté » (SPEC §6) n'est pas encore branchée.
- La détection d'objets ne tourne qu'1 frame d'analyse sur 2 (CPU) ; les
  compteurs de saisie/dissimulation sont exprimés en « updates » de cette
  cadence.
- `yolov8n` : le plus petit modèle — précision limitée en scène chargée ;
  remplaçable par `yolov8s/m` via `YOLO_MODEL`/`OBJECT_MODEL` sans changer le code.
