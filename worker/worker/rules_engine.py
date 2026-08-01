"""Moteur de règles de comportements (SPEC §6) — pur Python, testé par séquences
d'événements synthétiques.

Principe produit : l'IA signale, l'humain décide. Le moteur n'émet jamais un
verdict de « vol » ; il produit des alertes de comportement à vérifier, avec un
score et les indices (« evidence ») qui l'expliquent.

RGPD : l'état est indexé par des IDs de tracking éphémères et vit en mémoire du
processus ; il est purgé dès qu'un track devient inactif.
"""

import dataclasses
from dataclasses import dataclass, field

RULE_DISSIMULATION = "dissimulation"
RULE_PASSAGE_SANS_CAISSE = "passage_sans_caisse"
RULE_TEMPS_ANORMAL = "temps_anormal"
RULE_ZONE_INTERDITE = "zone_interdite"

SEVERITY_BY_RULE = {
    RULE_DISSIMULATION: "high",
    RULE_ZONE_INTERDITE: "high",
    RULE_PASSAGE_SANS_CAISSE: "medium",
    RULE_TEMPS_ANORMAL: "low",
}


@dataclass(frozen=True)
class RulesConfig:
    # Seuil combiné et anti-spam
    alert_threshold: float = 60.0
    cooldown_seconds: float = 60.0
    # Fenêtre de validité des indices ; au-delà, ils expirent sans alerte.
    window_seconds: float = 120.0
    state_ttl_seconds: float = 300.0

    # Règle 1 — dissimulation (séquence saisie → disparition → sortie du rayon)
    score_grab: float = 15.0
    score_conceal: float = 35.0
    score_conceal_without_grab: float = 20.0
    score_conceal_exit: float = 30.0

    # Règle 2 — passage en sortie sans passage caisse
    score_checkout_bypass: float = 65.0
    min_shelf_seconds: float = 10.0
    checkout_min_seconds: float = 5.0

    # Règle 3 — temps anormal en zone sensible avec faible mouvement
    score_abnormal_dwell: float = 40.0
    low_motion_radius: float = 0.05

    # Règle 4 — gestes d'observation : bonus uniquement, jamais seul (SPEC §6)
    score_gesture: float = 15.0

    # Règle 5 — zone interdite (réserve)
    score_forbidden_zone: float = 70.0

    @classmethod
    def from_dict(cls, data: dict | None) -> "RulesConfig":
        """Config par caméra : les clés inconnues sont ignorées."""
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass(frozen=True)
class AlertDecision:
    rule: str
    severity: str
    score: float
    ts: float
    track_id: int
    evidence: list[dict]


@dataclass
class _Finding:
    ts: float
    rule: str
    score: float
    detail: dict


@dataclass
class _TrackState:
    findings: list[_Finding] = field(default_factory=list)
    grab_ts: float | None = None
    conceal_ts: float | None = None
    # Temps cumulé par type de zone + zones en cours (zone_id -> (entrée, type)).
    zone_seconds: dict[str, float] = field(default_factory=dict)
    current_zones: dict[str, tuple[float, str]] = field(default_factory=dict)
    cooldown_until: float = 0.0
    last_event_ts: float = 0.0


SENSITIVE_ZONE_TYPES = ("rayon", "reserve")


class RulesEngine:
    """Consomme les événements d'analyse et décide des alertes.

    Événements attendus (dicts) : person_entered_zone, person_left_zone,
    person_dwell (+ movement_radius), object_grabbed, object_concealed,
    surveillance_gesture. Chaque événement porte track_id et ts.
    """

    def __init__(self, config: RulesConfig | None = None):
        self._config = config or RulesConfig()
        self._tracks: dict[int, _TrackState] = {}

    @property
    def config(self) -> RulesConfig:
        return self._config

    def update_config(self, config: RulesConfig) -> None:
        self._config = config

    def process(self, event: dict) -> list[AlertDecision]:
        track_id = event.get("track_id")
        ts = event.get("ts")
        if track_id is None or ts is None:
            return []

        state = self._tracks.setdefault(track_id, _TrackState())
        state.last_event_ts = ts

        handler = getattr(self, f"_on_{event['type']}", None)
        if handler is not None:
            handler(state, event, ts)

        decisions = self._evaluate(state, track_id, ts)
        self._prune_stale_tracks(ts)
        return decisions

    # --- Comptabilité de zones + règles déclenchées par les zones ---

    def _on_person_entered_zone(self, state: _TrackState, event: dict, ts: float) -> None:
        zone_type = event.get("zone_type", "autre")
        state.current_zones[event["zone_id"]] = (ts, zone_type)

        if zone_type == "reserve":
            self._add(state, ts, RULE_ZONE_INTERDITE, self._config.score_forbidden_zone,
                      {"stage": "entered_reserve", "zone_id": event["zone_id"]})

        if zone_type == "sortie":
            shelf = self._zone_total(state, "rayon", ts)
            checkout = self._zone_total(state, "caisse", ts)
            if (
                shelf >= self._config.min_shelf_seconds
                and checkout < self._config.checkout_min_seconds
            ):
                self._add(state, ts, RULE_PASSAGE_SANS_CAISSE,
                          self._config.score_checkout_bypass,
                          {"stage": "exit_without_checkout",
                           "shelf_seconds": round(shelf, 3),
                           "checkout_seconds": round(checkout, 3)})

    def _on_person_left_zone(self, state: _TrackState, event: dict, ts: float) -> None:
        zone_type = event.get("zone_type", "autre")
        entry = state.current_zones.pop(event["zone_id"], None)
        duration = event.get("duration_seconds")
        if duration is None and entry is not None:
            duration = ts - entry[0]
        if duration:
            state.zone_seconds[zone_type] = state.zone_seconds.get(zone_type, 0.0) + duration

        if zone_type == "rayon" and self._recent(state.conceal_ts, ts):
            self._add(state, ts, RULE_DISSIMULATION, self._config.score_conceal_exit,
                      {"stage": "left_shelf_after_conceal", "zone_id": event["zone_id"]})

    def _on_person_dwell(self, state: _TrackState, event: dict, ts: float) -> None:
        radius = event.get("movement_radius")
        if (
            event.get("zone_type") in SENSITIVE_ZONE_TYPES
            and radius is not None
            and radius <= self._config.low_motion_radius
        ):
            self._add(state, ts, RULE_TEMPS_ANORMAL, self._config.score_abnormal_dwell,
                      {"stage": "low_motion_dwell",
                       "dwell_seconds": event.get("dwell_seconds"),
                       "movement_radius": radius})

    # --- Perception (règles 1 et 4) ---

    def _on_object_grabbed(self, state: _TrackState, event: dict, ts: float) -> None:
        state.grab_ts = ts
        self._add(state, ts, RULE_DISSIMULATION, self._config.score_grab,
                  {"stage": "grab", "object_class": event.get("object_class")})

    def _on_object_concealed(self, state: _TrackState, event: dict, ts: float) -> None:
        if self._recent(state.grab_ts, ts):
            score = self._config.score_conceal
        else:
            score = self._config.score_conceal_without_grab
        state.conceal_ts = ts
        self._add(state, ts, RULE_DISSIMULATION, score,
                  {"stage": "conceal", "object_class": event.get("object_class")})

    def _on_surveillance_gesture(self, state: _TrackState, event: dict, ts: float) -> None:
        # Jamais seul (SPEC §6) : uniquement en renfort d'une séquence de dissimulation.
        if self._recent(state.grab_ts, ts) or self._recent(state.conceal_ts, ts):
            self._add(state, ts, RULE_DISSIMULATION, self._config.score_gesture,
                      {"stage": "surveillance_gesture", "count": event.get("count")})

    # --- Décision ---

    def _evaluate(self, state: _TrackState, track_id: int, ts: float) -> list[AlertDecision]:
        horizon = ts - self._config.window_seconds
        state.findings = [f for f in state.findings if f.ts >= horizon]
        total = sum(f.score for f in state.findings)
        if total < self._config.alert_threshold or ts < state.cooldown_until:
            return []

        dominant = max(state.findings, key=lambda f: f.score)
        evidence = [
            {"ts": f.ts, "rule": f.rule, "score": f.score, **f.detail}
            for f in state.findings
        ]
        decision = AlertDecision(
            rule=dominant.rule,
            severity=SEVERITY_BY_RULE[dominant.rule],
            score=round(total, 3),
            ts=ts,
            track_id=track_id,
            evidence=evidence,
        )
        # Cooldown + remise à zéro : la prochaine alerte exige des indices frais.
        state.cooldown_until = ts + self._config.cooldown_seconds
        state.findings = []
        state.grab_ts = None
        state.conceal_ts = None
        return [decision]

    # --- Aides ---

    def _add(self, state: _TrackState, ts: float, rule: str, score: float, detail: dict) -> None:
        state.findings.append(_Finding(ts=ts, rule=rule, score=score, detail=detail))

    def _recent(self, marker_ts: float | None, ts: float) -> bool:
        return marker_ts is not None and ts - marker_ts <= self._config.window_seconds

    def _zone_total(self, state: _TrackState, zone_type: str, ts: float) -> float:
        total = state.zone_seconds.get(zone_type, 0.0)
        for entered, ztype in state.current_zones.values():
            if ztype == zone_type:
                total += ts - entered
        return total

    def _prune_stale_tracks(self, ts: float) -> None:
        ttl = self._config.state_ttl_seconds
        for track_id in [
            tid for tid, s in self._tracks.items() if ts - s.last_event_ts > ttl
        ]:
            del self._tracks[track_id]
