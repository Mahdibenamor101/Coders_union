# SaaS de vidéosurveillance intelligente pour magasins

SaaS B2B qui analyse les flux des caméras IP existantes d'un commerce pour signaler
des comportements à vérifier par le personnel. **L'IA signale, l'humain décide** —
aucune reconnaissance faciale, aucune identification biométrique.

La spécification complète du produit est dans [SPEC.md](SPEC.md).

## Structure du dépôt

```
backend/    API FastAPI (REST + WebSockets) — Python 3.12
worker/     Worker vidéo : ingestion RTSP, buffer circulaire, clips — Python + OpenCV + ffmpeg
frontend/   Dashboard Next.js 14 + TypeScript + Tailwind (Phase 4)
scripts/    Outils de dev (flux RTSP de test généré)
```

## État d'avancement

| Phase | Contenu | État |
|---|---|---|
| 1 | Ingestion vidéo (RTSP, buffer, clips MinIO, CRUD) | ✅ — voir [PHASE1_README.md](PHASE1_README.md) |
| 2 | Détection et tracking (YOLO + ByteTrack, zones) | à venir |
| 3 | Moteur de comportements | à venir |
| 4 | Dashboard | à venir |
| 5 | SaaS (auth, Stripe, RGPD) | à venir |

## Démarrage rapide

```bash
cp .env.example .env   # puis renseigner API_KEY et FERNET_KEY
docker compose up -d --build
```

Le guide de test manuel de la phase en cours est dans [PHASE1_README.md](PHASE1_README.md).
