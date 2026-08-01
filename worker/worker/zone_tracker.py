"""Moteur d'entrées/sorties/dwell de zones — pur Python, sans dépendance IA.

RGPD : les IDs de tracking sont éphémères (mémoire du processus, une session
vidéo). Aucune position n'est persistée ; seuls des événements de zone sortent.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    type: str
    # Polygone en coordonnées normalisées [0,1] (indépendant de la résolution).
    polygon: tuple[tuple[float, float], ...]

    @classmethod
    def from_dict(cls, data: dict) -> "Zone":
        return cls(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            polygon=tuple((float(x), float(y)) for x, y in data["polygon"]),
        )


def point_in_polygon(x: float, y: float, polygon: tuple[tuple[float, float], ...]) -> bool:
    """Ray casting : le point est-il dans le polygone (bords inclus approximativement)."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


@dataclass
class _TrackState:
    zones: set[str] = field(default_factory=set)
    entered_at: dict[str, float] = field(default_factory=dict)
    dwell_emitted: set[str] = field(default_factory=set)
    last_seen: float = 0.0


class ZoneTracker:
    """Suit l'appartenance de chaque personne trackée aux zones et émet des événements.

    `process()` reçoit les détections d'une frame — (track_id, x, y) normalisés,
    point au sol de la personne — et retourne les événements :
    - person_entered_zone
    - person_left_zone (avec duration_seconds)
    - person_dwell (une fois par (track, zone), au-delà de dwell_seconds)

    Un track non revu depuis track_ttl secondes est expiré : sorties de zones
    émises puis état oublié (IDs éphémères).
    """

    def __init__(
        self,
        zones: list[Zone] | None = None,
        dwell_seconds: float = 30.0,
        track_ttl: float = 5.0,
    ):
        self._zones: list[Zone] = list(zones or [])
        self._dwell_seconds = dwell_seconds
        self._track_ttl = track_ttl
        self._tracks: dict[int, _TrackState] = {}

    def update_zones(self, zones: list[Zone]) -> None:
        """Remplace les zones à chaud ; les diffs d'appartenance sortiront à la frame suivante."""
        self._zones = list(zones)
        known = {z.id for z in self._zones}
        for state in self._tracks.values():
            state.zones &= known
            state.entered_at = {z: t for z, t in state.entered_at.items() if z in known}
            state.dwell_emitted &= known

    @property
    def zones(self) -> list[Zone]:
        return list(self._zones)

    def set_dwell_seconds(self, dwell_seconds: float) -> None:
        self._dwell_seconds = dwell_seconds

    def process(
        self, ts: float, detections: list[tuple[int, float, float]]
    ) -> list[dict]:
        events: list[dict] = []
        zones_by_id = {z.id: z for z in self._zones}

        for track_id, x, y in detections:
            state = self._tracks.setdefault(track_id, _TrackState())
            state.last_seen = ts
            current = {
                z.id for z in self._zones if point_in_polygon(x, y, z.polygon)
            }

            for zone_id in sorted(current - state.zones):
                state.entered_at[zone_id] = ts
                events.append(self._event("person_entered_zone", track_id, zones_by_id[zone_id], ts))

            for zone_id in sorted(state.zones - current):
                events.append(self._left_event(track_id, zones_by_id[zone_id], state, ts))

            for zone_id in sorted(current):
                if zone_id in state.dwell_emitted:
                    continue
                dwell = ts - state.entered_at.get(zone_id, ts)
                if dwell >= self._dwell_seconds:
                    state.dwell_emitted.add(zone_id)
                    event = self._event("person_dwell", track_id, zones_by_id[zone_id], ts)
                    event["dwell_seconds"] = round(dwell, 3)
                    events.append(event)

            state.zones = current

        # Expiration des tracks perdus : sortie de toutes leurs zones, puis oubli.
        for track_id in [
            tid
            for tid, s in self._tracks.items()
            if ts - s.last_seen > self._track_ttl
        ]:
            state = self._tracks.pop(track_id)
            for zone_id in sorted(state.zones):
                if zone_id in zones_by_id:
                    events.append(
                        self._left_event(track_id, zones_by_id[zone_id], state, ts)
                    )

        return events

    def _event(self, event_type: str, track_id: int, zone: Zone, ts: float) -> dict:
        return {
            "type": event_type,
            "track_id": track_id,
            "zone_id": zone.id,
            "zone_name": zone.name,
            "zone_type": zone.type,
            "ts": ts,
        }

    def _left_event(
        self, track_id: int, zone: Zone, state: _TrackState, ts: float
    ) -> dict:
        event = self._event("person_left_zone", track_id, zone, ts)
        entered = state.entered_at.pop(zone.id, None)
        event["duration_seconds"] = round(ts - entered, 3) if entered is not None else None
        return event
