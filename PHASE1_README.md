# Phase 1 — Ingestion vidéo

Fondation du pipeline : un worker se connecte à un flux RTSP, maintient un buffer
circulaire de ~60 s en mémoire, et découpe à la demande un clip (20 s avant / 20 s
après un événement) qu'il uploade sur MinIO. L'API expose le CRUD
tenants / magasins / caméras et le déclenchement de clips.

## Architecture de la phase

```
test-stream (ffmpeg, mire générée)
      │ RTSP
      ▼
   mediamtx ◀── worker (OpenCV, 8 fps, buffer 60 s) ──▶ MinIO (clips .mp4)
                   ▲ commandes Redis    │ événements Redis
                   │                    ▼
                 API FastAPI ──▶ PostgreSQL
```

- `POST /cameras/{id}/clip` → l'API publie `extract_clip` sur `camera_commands:{id}`.
- Le worker attend la fin de la fenêtre « après », assemble le MP4 depuis le buffer,
  l'uploade sur `s3://clips/{camera_id}/{clip_id}.mp4` et publie `clip_ready` sur
  `worker_events` ; l'API passe alors le clip à `ready`.
- Le worker publie aussi un statut caméra (`online`/`offline`) toutes les 10 s.
- Les URLs RTSP sont chiffrées (Fernet) en base et ne sont jamais renvoyées par le
  CRUD ; seul `GET /cameras/{id}/stream-url` (clé API) les déchiffre, pour les workers.

## Test manuel de bout en bout

### 1. Préparer l'environnement

```bash
cp .env.example .env
# Renseigner API_KEY (valeur libre) et FERNET_KEY :
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Démarrer l'infrastructure

```bash
docker compose up -d --build postgres redis minio mediamtx test-stream api
curl http://localhost:8000/health   # → {"status":"ok"}
```

Le flux de test (mire générée, aucune image réelle) est visible avec :
`ffplay rtsp://localhost:8554/teststream`.

### 3. Enregistrer tenant → magasin → caméra

```bash
export KEY="votre-API_KEY"

TENANT=$(curl -s -X POST http://localhost:8000/tenants \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"name": "Boutique Démo"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

STORE=$(curl -s -X POST http://localhost:8000/stores \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d "{\"tenant_id\": \"$TENANT\", \"name\": \"Magasin Centre\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

CAMERA=$(curl -s -X POST http://localhost:8000/cameras \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d "{\"store_id\": \"$STORE\", \"name\": \"Entrée\", \"rtsp_url\": \"rtsp://mediamtx:8554/teststream\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "Camera: $CAMERA"
```

### 4. Démarrer le worker sur cette caméra

```bash
# Dans .env : WORKER_CAMERA_ID=<valeur de $CAMERA>
docker compose up -d worker
docker compose logs -f worker   # attendre "RTSP connected"
```

Après ~10 s, la caméra passe `online` :

```bash
curl -s http://localhost:8000/cameras/$CAMERA -H "X-API-Key: $KEY"
```

### 5. Déclencher un clip (critère de fin de phase)

```bash
# Laisser le buffer se remplir ~30 s, puis :
CLIP=$(curl -s -X POST http://localhost:8000/cameras/$CAMERA/clip \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Le worker attend 20 s (fenêtre « après ») puis uploade. Vérifier :
curl -s http://localhost:8000/clips/$CLIP -H "X-API-Key: $KEY"   # status: "ready"
curl -s http://localhost:8000/clips/$CLIP/url -H "X-API-Key: $KEY"  # URL présignée
```

Le clip est aussi visible dans la console MinIO : http://localhost:9001
(identifiants `S3_ACCESS_KEY` / `S3_SECRET_KEY`), bucket `clips`.

## Tests automatisés

```bash
# Backend (CRUD, chiffrement RTSP, commandes/événements Redis)
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

# Worker (buffer circulaire)
cd ../worker && ../backend/.venv/bin/pytest
```

## Limites connues (assumées en Phase 1)

- Auth par clé API unique — JWT, rôles et isolation multi-tenant en Phase 5.
- Les clips sont reconstruits depuis les frames échantillonnées (8 fps) : fluidité
  réduite mais suffisante pour la vérification humaine ; sera raffiné si besoin.
- `create_all` au démarrage — migrations Alembic dès que le schéma évoluera.
- Un seul worker configuré via `WORKER_CAMERA_ID` ; la supervision d'un worker par
  caméra arrive avec les phases suivantes.
