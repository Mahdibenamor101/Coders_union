"""Scénarios simulés de bout en bout (logique) : perception → zones → règles.

Critère de fin de Phase 3 : un scénario de dissimulation produit une alerte,
un scénario de shopping normal n'en produit pas. Ici la chaîne complète des
composants est rejouée avec des détections synthétiques (sans modèle IA).
"""

from worker.perception import ObjectAssociationTracker, PersonObs
from worker.rules_engine import RULE_DISSIMULATION, RulesEngine
from worker.zone_tracker import Zone, ZoneTracker

SHELF = Zone(
    id="rayon1",
    name="Rayon",
    type="rayon",
    polygon=((0.0, 0.0), (0.6, 0.0), (0.6, 1.0), (0.0, 1.0)),
)
CHECKOUT = Zone(
    id="caisse1",
    name="Caisse",
    type="caisse",
    polygon=((0.6, 0.0), (0.8, 0.0), (0.8, 1.0), (0.6, 1.0)),
)
EXIT = Zone(
    id="sortie1",
    name="Sortie",
    type="sortie",
    polygon=((0.8, 0.0), (1.0, 0.0), (1.0, 1.0), (0.8, 1.0)),
)


class Simulation:
    def __init__(self):
        self.zone_tracker = ZoneTracker([SHELF, CHECKOUT, EXIT])
        self.association = ObjectAssociationTracker(
            min_hold_updates=2, conceal_updates=3
        )
        self.engine = RulesEngine()
        self.alerts = []

    def step(self, ts, x, y, objects=()):
        person = PersonObs(
            track_id=1,
            foot=(x, y),
            bbox=(x - 0.05, y - 0.3, x + 0.05, y),
            wrists=((x, y - 0.15),),
        )
        events = self.zone_tracker.process(ts, [(1, x, y)])
        objects_near = [
            ("bottle", (ox - 0.02, oy - 0.02, ox + 0.02, oy + 0.02))
            for ox, oy in objects
        ]
        events += self.association.update(ts, [person], objects_near)
        for event in events:
            self.alerts.extend(self.engine.process(event))


def test_concealment_scenario_produces_alert():
    sim = Simulation()
    hand = lambda x, y: [(x, y - 0.15)]  # objet dans la main

    # La personne entre dans le rayon, prend une bouteille…
    sim.step(0.0, 0.3, 0.5)
    sim.step(1.0, 0.3, 0.5, objects=hand(0.3, 0.5))
    sim.step(2.0, 0.3, 0.5, objects=hand(0.3, 0.5))  # object_grabbed
    # … la bouteille disparaît (sac/poche) sans réapparaître…
    sim.step(3.0, 0.3, 0.5)
    sim.step(4.0, 0.3, 0.5)
    sim.step(5.0, 0.3, 0.5)  # object_concealed
    # … puis la personne quitte le rayon (vers l'allée caisse).
    sim.step(10.0, 0.7, 0.5)

    assert len(sim.alerts) >= 1
    alert = sim.alerts[0]
    assert alert.rule == RULE_DISSIMULATION
    assert alert.severity == "high"
    stages = [e.get("stage") for e in alert.evidence]
    assert "grab" in stages and "conceal" in stages


def test_normal_shopping_produces_no_alert():
    sim = Simulation()

    # La personne parcourt le rayon, la bouteille reste visible dans sa main,
    # elle passe en caisse puis sort.
    for ts in range(0, 15):
        x = 0.3 + ts * 0.01
        sim.step(float(ts), x, 0.5, objects=[(x, 0.35)])
    for ts in range(15, 25):  # passage en caisse (10 s > checkout_min_seconds)
        sim.step(float(ts), 0.7, 0.5, objects=[(0.7, 0.35)])
    sim.step(25.0, 0.9, 0.5, objects=[(0.9, 0.35)])  # sortie

    assert sim.alerts == []


def test_browsing_without_grab_produces_no_alert():
    sim = Simulation()
    # Flânerie en rayon sans toucher d'objet, puis passage caisse et sortie.
    for ts in range(0, 30, 2):
        sim.step(float(ts), 0.2 + (ts % 8) * 0.03, 0.4)
    for ts in range(30, 40, 2):
        sim.step(float(ts), 0.7, 0.5)
    sim.step(40.0, 0.9, 0.5)
    assert sim.alerts == []
