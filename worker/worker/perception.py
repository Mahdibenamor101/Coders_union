"""Couche perception (SPEC §6, règles 1 et 4) — logique pure, testable sans modèle.

Produit des événements de niveau signal à partir des sorties YOLO/pose :
- object_grabbed : un objet est associé de façon stable à la main d'une personne.
- object_concealed : un objet saisi disparaît des détections sans réapparaître.
- surveillance_gesture : rotations de tête répétées (posture d'observation).

Ces heuristiques sont volontairement simples et ajustables ; c'est le moteur de
règles qui combine les signaux et décide, jamais la perception seule.
"""

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PersonObs:
    """Observation d'une personne sur une frame (coordonnées normalisées [0,1])."""

    track_id: int
    foot: tuple[float, float]
    bbox: tuple[float, float, float, float]
    wrists: tuple[tuple[float, float], ...] = ()
    # Direction horizontale de la tête (nez vs épaules), ~[-1.5, 1.5] ; None sans pose.
    head_dir: float | None = None


@dataclass
class _HeldObject:
    object_class: str
    hold_updates: int = 0
    grabbed: bool = False
    missing_updates: int = 0
    concealed: bool = False


@dataclass
class _PersonAssocState:
    objects: dict[str, _HeldObject] = field(default_factory=dict)
    last_seen: float = 0.0


class ObjectAssociationTracker:
    """Associe les objets détectés aux mains des personnes et détecte la séquence
    « objet saisi → objet non visible » (règle 1, partie perception).

    `update()` n'est appelé que sur les frames où la détection d'objets a tourné.
    """

    def __init__(
        self,
        hand_radius: float = 0.08,
        min_hold_updates: int = 3,
        conceal_updates: int = 8,
        person_ttl: float = 5.0,
    ):
        self._hand_radius = hand_radius
        self._min_hold_updates = min_hold_updates
        self._conceal_updates = conceal_updates
        self._person_ttl = person_ttl
        self._persons: dict[int, _PersonAssocState] = {}

    def update(
        self,
        ts: float,
        persons: list[PersonObs],
        objects: list[tuple[str, tuple[float, float, float, float]]],
    ) -> list[dict]:
        events: list[dict] = []

        for person in persons:
            state = self._persons.setdefault(person.track_id, _PersonAssocState())
            state.last_seen = ts
            near = {
                cls for cls, bbox in objects if self._near_person(person, bbox)
            }

            for cls in near:
                obj = state.objects.setdefault(cls, _HeldObject(cls))
                if obj.concealed:
                    # L'objet réapparaît : la dissimulation est invalidée.
                    state.objects[cls] = obj = _HeldObject(cls)
                obj.missing_updates = 0
                obj.hold_updates += 1
                if not obj.grabbed and obj.hold_updates >= self._min_hold_updates:
                    obj.grabbed = True
                    events.append(
                        {
                            "type": "object_grabbed",
                            "track_id": person.track_id,
                            "object_class": cls,
                            "ts": ts,
                        }
                    )

            for cls in list(state.objects):
                if cls in near:
                    continue
                obj = state.objects[cls]
                if obj.grabbed and not obj.concealed:
                    obj.missing_updates += 1
                    if obj.missing_updates >= self._conceal_updates:
                        obj.concealed = True
                        events.append(
                            {
                                "type": "object_concealed",
                                "track_id": person.track_id,
                                "object_class": cls,
                                "ts": ts,
                            }
                        )
                elif not obj.grabbed:
                    obj.hold_updates -= 1
                    if obj.hold_updates <= 0:
                        del state.objects[cls]

        self._persons = {
            tid: s
            for tid, s in self._persons.items()
            if ts - s.last_seen <= self._person_ttl
        }
        return events

    def _near_person(
        self, person: PersonObs, bbox: tuple[float, float, float, float]
    ) -> bool:
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        if person.wrists:
            return any(
                math.dist((cx, cy), wrist) <= self._hand_radius
                for wrist in person.wrists
            )
        # Sans pose : repli grossier sur la bounding box de la personne.
        x1, y1, x2, y2 = person.bbox
        margin = 0.05
        return (x1 - margin) <= cx <= (x2 + margin) and (y1 - margin) <= cy <= (y2 + margin)


@dataclass
class _GestureState:
    last_side: str | None = None
    changes: deque = field(default_factory=deque)
    last_seen: float = 0.0


class GestureMonitor:
    """Compte les alternances gauche/droite marquées de la tête (règle 4).

    Émet `surveillance_gesture` quand `min_changes` alternances surviennent dans
    la fenêtre. Le moteur de règles n'en tient compte qu'en renfort de la règle 1.
    """

    def __init__(
        self,
        min_amplitude: float = 0.3,
        min_changes: int = 3,
        window_seconds: float = 10.0,
        track_ttl: float = 30.0,
    ):
        self._min_amplitude = min_amplitude
        self._min_changes = min_changes
        self._window = window_seconds
        self._track_ttl = track_ttl
        self._tracks: dict[int, _GestureState] = {}

    def update(self, ts: float, track_id: int, head_dir: float | None) -> dict | None:
        self._tracks = {
            tid: s
            for tid, s in self._tracks.items()
            if ts - s.last_seen <= self._track_ttl
        }
        if head_dir is None:
            return None

        state = self._tracks.setdefault(track_id, _GestureState())
        state.last_seen = ts

        side = None
        if head_dir <= -self._min_amplitude:
            side = "left"
        elif head_dir >= self._min_amplitude:
            side = "right"

        if side is not None:
            if state.last_side is not None and side != state.last_side:
                state.changes.append(ts)
            state.last_side = side

        while state.changes and ts - state.changes[0] > self._window:
            state.changes.popleft()

        if len(state.changes) >= self._min_changes:
            count = len(state.changes)
            state.changes.clear()
            return {
                "type": "surveillance_gesture",
                "track_id": track_id,
                "count": count,
                "ts": ts,
            }
        return None


class MovementTracker:
    """Rayon de déplacement récent par track (pour le « faible mouvement » de la
    règle 3). Positions en mémoire uniquement, bornées par la fenêtre."""

    def __init__(self, window_seconds: float = 60.0):
        self._window = window_seconds
        self._points: dict[int, deque] = {}

    def add(self, ts: float, track_id: int, x: float, y: float) -> None:
        points = self._points.setdefault(track_id, deque())
        points.append((ts, x, y))
        while points and ts - points[0][0] > self._window:
            points.popleft()

    def radius(self, track_id: int) -> float | None:
        points = self._points.get(track_id)
        if not points or len(points) < 2:
            return None
        cx = sum(p[1] for p in points) / len(points)
        cy = sum(p[2] for p in points) / len(points)
        return max(math.dist((cx, cy), (x, y)) for _, x, y in points)

    def forget(self, track_id: int) -> None:
        self._points.pop(track_id, None)
