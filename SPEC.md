# SPEC.md — SaaS de vidéosurveillance intelligente pour magasins

> Ce document est la spécification de référence du projet. Lis-le entièrement avant toute implémentation. Travaille phase par phase : n'implémente une phase que lorsque je te le demande explicitement, et ne passe jamais à la phase suivante sans validation.

## 1. Vision du produit

Un SaaS B2B destiné aux commerces de détail (boutiques, supermarchés, pharmacies) qui :
- Se connecte aux caméras IP existantes du magasin (flux RTSP).
- Analyse les flux vidéo en continu avec de l'IA pour détecter des comportements suspects liés au vol à l'étalage.
- Envoie des alertes en temps réel au personnel (dashboard web + notifications).
- Conserve un historique des incidents avec clips vidéo horodatés pour vérification humaine.
- Gère plusieurs magasins et plusieurs utilisateurs par client (multi-tenant).

Principe fondamental : **l'IA signale, l'humain décide.** Le système ne qualifie jamais quelqu'un de "voleur" ; il génère des alertes de comportement à vérifier par un employé. Ce principe doit se refléter dans le vocabulaire de l'UI ("comportement à vérifier", jamais "vol détecté") et dans le modèle de données (chaque alerte a un statut de revue humaine).

## 2. Contraintes légales (RGPD / AI Act — non négociables)

- **Aucune reconnaissance faciale, aucune identification biométrique.** Ne jamais intégrer de modèle de face recognition, même en option.
- Pas de scoring persistant des personnes : les identifiants de tracking sont éphémères (durée de vie = une session vidéo, jamais recoupés entre jours ou magasins).
- Rétention limitée : clips d'incidents conservés 30 jours par défaut (configurable par tenant, max 90 jours), flux bruts non conservés au-delà du buffer d'analyse (quelques minutes).
- Suppression automatique planifiée (job cron) + suppression manuelle possible.
- Journal d'audit : chaque visionnage de clip par un utilisateur est loggé (qui, quoi, quand).
- Chiffrement au repos (stockage vidéo) et en transit (TLS partout).
- Prévoir un endpoint d'export/suppression des données par tenant (droit d'accès et à l'effacement).

## 3. Stack technique

| Composant | Choix | Rôle |
|---|---|---|
| Backend API | Python 3.12 + FastAPI | API REST + WebSockets |
| Worker vidéo | Python + OpenCV + ffmpeg | Ingestion RTSP, extraction de frames, découpe de clips |
| Détection | Ultralytics YOLOv8 (ou v11) | Détection de personnes et d'objets |
| Tracking | ByteTrack (intégré à Ultralytics) | Suivi des personnes entre les frames |
| Analyse comportement | Règles + pose estimation (YOLOv8-pose) ; en option, API vision multimodale pour lever l'ambiguïté sur les cas incertains | Détection de comportements suspects |
| File de messages | Redis (pub/sub + queues) | Communication worker → API → dashboard |
| Base de données | PostgreSQL 16 | Données métier, multi-tenant |
| Stockage clips | S3-compatible (MinIO en dev) | Clips vidéo d'incidents |
| Frontend | Next.js 14 + TypeScript + Tailwind | Dashboard |
| Temps réel | WebSockets (FastAPI) | Alertes live |
| Auth | Auth par email/mot de passe + JWT, rôles par tenant | — |
| Paiement | Stripe (abonnements) | Phase 5 uniquement |
| Déploiement | Docker Compose en dev ; worker GPU séparé de l'API | — |

Choix par défaut : IA en local (YOLO) pour le flux continu. Ne pas envoyer chaque frame à une API cloud (coût et latence prohibitifs). Une API multimodale peut être appelée ponctuellement, uniquement sur les séquences déjà signalées par les règles locales, pour réduire les faux positifs.

## 4. Architecture

```
Caméras IP (RTSP)
      │
      ▼
[Worker vidéo]  ── frames ──▶ [Pipeline IA: YOLO + ByteTrack + règles]
      │                               │
      │ clips (S3/MinIO)              │ événements (Redis)
      ▼                               ▼
   [Stockage]                   [API FastAPI] ──▶ PostgreSQL
                                      │
                                      │ WebSocket
                                      ▼
                              [Dashboard Next.js]
```

- Un worker par flux caméra (processus indépendants, supervisés).
- Le worker maintient un buffer circulaire de ~60 s de vidéo : quand une alerte est levée, il extrait un clip de 20 s avant → 20 s après l'événement.
- L'API ne touche jamais aux flux vidéo bruts ; elle ne manipule que les événements et les clips finalisés.

## 5. Modèle de données (tables principales)

- `tenants` (id, nom, plan, paramètres de rétention)
- `users` (id, tenant_id, email, rôle: admin | manager | viewer)
- `stores` (id, tenant_id, nom, adresse, fuseau horaire)
- `cameras` (id, store_id, nom, url_rtsp chiffrée, zones configurées en JSON, statut)
- `zones` : polygones dessinés sur l'image caméra, typés (rayon, caisse, entrée/sortie, réserve)
- `alerts` (id, camera_id, type, sévérité, timestamp, clip_url, thumbnail_url, statut_revue: pending | confirmed | false_positive | dismissed, reviewed_by, reviewed_at, métadonnées JSON)
- `audit_logs` (id, user_id, action, cible, timestamp)

Toutes les requêtes sont filtrées par tenant_id (middleware). Aucune donnée ne doit fuiter entre tenants.

## 6. Détection des comportements suspects (Phase 3 — cœur du produit)

Approche : moteur de règles sur les sorties de YOLO + tracking + pose, pas de "détecteur de vol" magique.

Signaux à implémenter, par ordre de priorité :

1. **Dissimulation** : une personne prend un objet (objet détecté dans la main / proximité main-rayon via pose) puis l'objet disparaît près du corps (sac, poche) sans réapparaître. Signal = séquence "objet saisi → objet non visible → personne quitte la zone rayon".
2. **Passage caisse sans transaction** : personne trackée entrant en zone "sortie" en provenance des rayons sans passage par la zone "caisse" au-delà d'un temps minimal.
3. **Temps anormal en zone** : durée en zone sensible > seuil configurable, avec faible mouvement.
4. **Gestes d'observation** : rotations de tête répétées / posture de surveillance (via pose estimation) combinées au signal 1 — jamais seul, trop de faux positifs.
5. **Zone interdite** : entrée en réserve / derrière un comptoir hors personnel.

Chaque règle produit un score ; une alerte n'est émise qu'au-delà d'un seuil combiné, avec un cooldown par personne trackée pour éviter le spam. Tous les seuils sont configurables par caméra dans le dashboard.

Étape optionnelle de réduction des faux positifs : envoyer les frames clés d'une séquence signalée à une API vision multimodale avec un prompt de description factuelle, et ajuster le score selon la réponse. Cette étape doit être désactivable par tenant.

## 7. Phases de développement

### Phase 1 — Ingestion vidéo (fondation)
- Docker Compose : PostgreSQL, Redis, MinIO, API, un worker.
- Worker : connexion à un flux RTSP (prévoir un flux de test via ffmpeg + fichier vidéo en boucle), extraction de frames à 5–10 fps, buffer circulaire, découpe de clips à la demande, upload MinIO.
- API : CRUD tenants/stores/cameras (sans auth complète à ce stade, une clé API simple suffit).
- Critère de fin : je peux enregistrer une caméra, le worker se connecte, et je peux déclencher manuellement l'extraction d'un clip qui apparaît dans MinIO.

### Phase 2 — Détection et tracking
- Intégration YOLOv8 + ByteTrack dans le worker.
- Détection de personnes avec IDs de tracking éphémères, positions stockées en mémoire (pas en base).
- Éditeur de zones : endpoint pour enregistrer des polygones par caméra ; détection d'entrée/sortie de zone.
- Événements publiés sur Redis : `person_entered_zone`, `person_left_zone`, `person_dwell`.
- Critère de fin : sur une vidéo de test, les logs montrent les entrées/sorties de zones avec IDs de tracking cohérents.

### Phase 3 — Moteur de comportements
- Implémentation des règles de la section 6 (dans l'ordre 1 → 5).
- Génération d'alertes : score, clip automatique (buffer), thumbnail, écriture en base, publication Redis.
- Jeu de tests : scénarios vidéo simulés + tests unitaires du moteur de règles avec des séquences d'événements synthétiques.
- Critère de fin : une vidéo de test avec un scénario de dissimulation produit une alerte avec clip, et une vidéo de shopping normal n'en produit pas.

### Phase 4 — Dashboard
- Next.js : login, vue live des alertes (WebSocket), liste des incidents avec player vidéo, workflow de revue (confirmer / faux positif / ignorer), éditeur visuel de zones sur snapshot caméra, réglage des seuils, stats (alertes/jour, taux de faux positifs par règle).
- Le taux de faux positifs par règle est essentiel : c'est ce qui permet d'ajuster les seuils.
- Critère de fin : parcours complet caméra → alerte → revue humaine, sans toucher au terminal.

### Phase 5 — SaaS
- Auth complète (JWT, rôles, invitations par email), isolation multi-tenant vérifiée par tests, Stripe (plans par nombre de caméras), page d'onboarding, jobs de rétention/suppression RGPD, journal d'audit, endpoint d'export de données.
- Critère de fin : deux tenants distincts ne voient jamais les données l'un de l'autre (test automatisé), et un abonnement Stripe en mode test fonctionne de bout en bout.

## 8. Conventions de travail

- Tests : pytest côté backend ; le moteur de règles (section 6) doit être testé unitairement à ≥ 80 %.
- Chaque phase = une branche, avec un README de phase expliquant comment tester manuellement.
- Pas de secrets en dur : tout en variables d'environnement (`.env.example` maintenu à jour).
- Les URLs RTSP contiennent des identifiants : les chiffrer en base.
- Vidéos de test : utiliser des vidéos libres de droits ou générées, jamais de vraies images de clients pendant le développement.
- Avant d'implémenter, propose un court plan (fichiers touchés, approche) et attends ma validation si la phase implique un choix structurant.

## 9. Hors périmètre (ne pas implémenter)

- Reconnaissance faciale ou toute identification de personnes.
- Application mobile (plus tard).
- Enregistrement continu type NVR : on ne stocke que les clips d'incidents.
- Détection d'employés vs clients.
