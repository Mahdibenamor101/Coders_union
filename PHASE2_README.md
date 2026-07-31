# Phase 2 — Détection et tracking

Le worker exécute désormais YOLOv8 (modèle `yolov8n`, personnes uniquement) +
ByteTrack sur le flux, et un moteur de zones émet des événements Redis quand une
personne trackée entre, sort ou s'attarde dans une zone dessinée sur l'image.

## Ce qui est en place

- **Détection + tracking** (`worker/worker/detection.py`) : YOLOv8 via
  Ultralytics, classe « personne » seulement, IDs ByteTrack **éphémères** —
  mémoire du processus, jamais persistés ni recoupés entre sessions (RGPD).
  Le point suivi est le point au sol (centre-bas de la bounding box), en
  coordonnées normalisées.
- **Zones** : `PUT /cameras/{id}/zones` enregistre des polygones normalisés
  ([0,1]²) typés `rayon | caisse | entree | sortie | reserve | autre`. L'API
  notifie le worker via Redis (`update_zones`) — prise en compte à chaud.
- **Moteur de zones** (`worker/worker/zone_tracker.py`, pur Python, testé
  unitairement) : entrées/sorties par ray casting, durée par zone, dwell,
  expiration des tracks perdus après `TRACK_TTL_SECONDS`.
- **Événements** publiés sur le canal Redis `analysis_events` et loggés :
  - `person_entered_zone` — `{camera_id, track_id, zone_id, zone_name, zone_type, ts}`
  - `person_left_zone` — idem + `duration_seconds`
  - `person_dwell` — idem + `dwell_seconds` (émis une fois par (track, zone)
    au-delà de `DWELL_SECONDS`)

Aucune position n'est stockée en base : seuls les événements de zone sortent du
worker. L'analyse est désactivable (`ANALYSIS_ENABLED=false`).

## Test manuel (critère de fin de phase)

Pré-requis : la stack Phase 1 fonctionne (voir PHASE1_README.md, étapes 1 à 4).

### 1. Diffuser une vidéo avec des personnes

La mire par défaut ne contient personne. Utiliser une vidéo **libre de droits**
(ex. une scène de rue ou de magasin sur pexels.com/videos) :

```bash
docker compose stop test-stream
./scripts/stream_video.sh ~/Téléchargements/video-libre.mp4
```

### 2. Dessiner des zones sur la caméra

Les coordonnées sont normalisées : (0,0) en haut à gauche, (1,1) en bas à droite.

```bash
curl -s -X PUT http://localhost:8000/cameras/$CAMERA/zones \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{
    "zones": [
      {"name": "Rayon gauche", "type": "rayon",
       "polygon": [[0.0, 0.2], [0.5, 0.2], [0.5, 1.0], [0.0, 1.0]]},
      {"name": "Sortie", "type": "sortie",
       "polygon": [[0.8, 0.0], [1.0, 0.0], [1.0, 1.0], [0.8, 1.0]]}
    ]}'
```

Le worker logge `zones updated (2 zones)`.

### 3. Observer les événements

Logs du worker (critère : entrées/sorties avec IDs de tracking cohérents) :

```bash
docker compose logs -f worker
# ... person_entered_zone track=3 zone=Rayon gauche (rayon)
# ... person_left_zone track=3 zone=Rayon gauche (rayon) duration=12.4s
```

Ou directement le canal Redis :

```bash
docker compose exec redis redis-cli SUBSCRIBE analysis_events
```

## Tests automatisés

```bash
cd backend && .venv/bin/pytest        # 21 tests (dont zones : validation, notification worker)
cd ../worker && ../backend/.venv/bin/pytest   # 13 tests (buffer + moteur de zones)
```

## Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `ANALYSIS_ENABLED` | `true` | Coupe toute l'analyse si `false` |
| `YOLO_MODEL` | `yolov8n.pt` | Modèle Ultralytics (poids pré-téléchargés dans l'image) |
| `ANALYSIS_FPS` | `5` | Cadence max d'analyse (le clip reste à `TARGET_FPS`) |
| `DWELL_SECONDS` | `30` | Seuil du signal `person_dwell` |
| `TRACK_TTL_SECONDS` | `5` | Expiration d'un track non revu |

## Limites assumées

- CPU par défaut (`yolov8n`) : ~2–5 fps d'analyse selon la machine — suffisant
  pour valider la logique ; le worker GPU dédié arrive avec le déploiement.
- Les seuils sont globaux au worker ; le réglage par caméra depuis le dashboard
  arrive en Phase 4 (l'API stocke déjà les zones par caméra).
- `person_dwell` ne mesure pas encore le « faible mouvement » (règle 3 complète
  en Phase 3).
