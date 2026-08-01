# Phase 5 — SaaS

Auth complète, isolation multi-tenant vérifiée par tests, Stripe, onboarding,
RGPD (rétention automatique, audit, export, effacement).

## Auth et rôles

- **Onboarding** : `/register` crée l'organisation (tenant) et son premier
  utilisateur (admin). Plan de départ : `starter`.
- **JWT** (24 h) porté en `Authorization: Bearer` ; le WebSocket prend
  `?token=` et ne diffuse que les alertes du tenant.
- **Rôles** : `viewer` (lecture), `manager` (magasins/caméras/zones/seuils,
  revue d'alertes, clips), `admin` (+ équipe, invitations, abonnement, RGPD).
- **Invitations** : `POST /invitations` (admin) génère un lien
  `/invitation?token=…` valable 7 jours, à usage unique. Le lien est retourné à
  l'admin (page Équipe) — brancher un SMTP en production pour l'envoyer par email.
- La clé API (`X-API-Key`) devient une **clé de service** réservée aux workers
  (`/internal/cameras/{id}/stream-url|zones|settings`) : elle ne donne plus
  accès aux endpoints utilisateurs.

## Isolation multi-tenant (critère de fin de phase)

Toutes les requêtes sont filtrées par le `tenant_id` du JWT (jointures
caméra → magasin → tenant). `backend/tests/test_isolation.py` vérifie avec deux
tenants peuplés que listes, objets, zones, seuils, clips, alertes, stats,
équipe et journal d'audit ne fuient jamais : tout accès croisé répond 404.

## Stripe — plans par nombre de caméras

| Plan | Caméras | Prix |
|---|---|---|
| starter | 2 | gratuit (défaut) |
| pro | 10 | prix Stripe `STRIPE_PRICE_PRO` |
| business | 50 | prix Stripe `STRIPE_PRICE_BUSINESS` |

- La création de caméra au-delà de la limite du plan répond **402**.
- `POST /billing/checkout-session` (admin) → URL Stripe Checkout
  (mode abonnement) ; `POST /billing/webhook` (signé) applique
  `checkout.session.completed` / `customer.subscription.updated|deleted`.
- Sans clés Stripe dans `.env`, la facturation est désactivée (503) et tout le
  monde reste en `starter`.

Test de bout en bout en mode test Stripe :

```bash
# 1. Renseigner STRIPE_SECRET_KEY (clé test), créer 2 prix récurrents et
#    reporter leurs IDs dans STRIPE_PRICE_PRO / STRIPE_PRICE_BUSINESS.
stripe listen --forward-to localhost:8000/billing/webhook   # → STRIPE_WEBHOOK_SECRET
# 2. Dashboard → Abonnement → « Passer à Pro » → carte 4242 4242 4242 4242.
# 3. Le webhook passe le tenant en plan pro (10 caméras).
```

La logique webhook/limites est couverte par les tests (`test_billing.py`,
événements Stripe simulés) ; le parcours réel nécessite vos clés de test.

## RGPD

- **Rétention automatique** : job périodique dans l'API (quotidien) qui purge
  clips et alertes plus vieux que la rétention du tenant (30 j défaut, 90 max),
  médias S3 compris. Suppression manuelle : `DELETE /alerts/{id}`.
- **Journal d'audit** : login, invitations, revues, **chaque visionnage de
  clip** (`clip_viewed`), export, suppressions — `GET /audit-logs` (admin).
- **Droit d'accès** : `GET /export` (admin) → JSON complet du tenant, sans
  secrets (ni hash de mots de passe, ni URLs RTSP).
- **Droit à l'effacement** : `DELETE /tenant/data` (admin) supprime base +
  médias S3 du tenant entier.

## Dashboard

Nouvelles pages : `/register` (onboarding), `/invitation` (activation de
compte), `/users` (équipe + invitations, admin), `/billing` (plans + checkout,
admin). Le login passe à email/mot de passe ; la revue d'alerte est signée du
compte connecté.

## Vérifications

```bash
cd backend && .venv/bin/pytest        # 51 tests (auth, rôles, isolation, billing, RGPD)
cd frontend && npm run build          # 13 pages
```

## Limites assumées

- Envoi d'email d'invitation non branché (lien retourné à l'admin) — prévoir
  un SMTP/service transactionnel en production.
- Pas de refresh token ni de révocation fine (JWT 24 h ; la suppression d'un
  utilisateur invalide ses tokens au prochain appel).
- Le parcours Stripe réel demande des clés de test (non fournies dans le dépôt).
