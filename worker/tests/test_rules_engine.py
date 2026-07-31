from worker.rules_engine import (
    RULE_DISSIMULATION,
    RULE_PASSAGE_SANS_CAISSE,
    RULE_TEMPS_ANORMAL,
    RULE_ZONE_INTERDITE,
    RulesConfig,
    RulesEngine,
)


def enter(tid, zone_id, zone_type, ts):
    return {
        "type": "person_entered_zone",
        "track_id": tid,
        "zone_id": zone_id,
        "zone_type": zone_type,
        "ts": ts,
    }


def leave(tid, zone_id, zone_type, ts, duration=None):
    return {
        "type": "person_left_zone",
        "track_id": tid,
        "zone_id": zone_id,
        "zone_type": zone_type,
        "ts": ts,
        "duration_seconds": duration,
    }


def dwell(tid, zone_type, ts, radius, seconds=45.0):
    return {
        "type": "person_dwell",
        "track_id": tid,
        "zone_id": "z",
        "zone_type": zone_type,
        "ts": ts,
        "dwell_seconds": seconds,
        "movement_radius": radius,
    }


def grabbed(tid, ts, cls="bottle"):
    return {"type": "object_grabbed", "track_id": tid, "object_class": cls, "ts": ts}


def concealed(tid, ts, cls="bottle"):
    return {"type": "object_concealed", "track_id": tid, "object_class": cls, "ts": ts}


def gesture(tid, ts, count=3):
    return {"type": "surveillance_gesture", "track_id": tid, "count": count, "ts": ts}


def run(engine, events):
    decisions = []
    for event in events:
        decisions.extend(engine.process(event))
    return decisions


class TestConcealment:
    def test_full_sequence_raises_alert(self):
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                enter(1, "r1", "rayon", 0.0),
                grabbed(1, 5.0),            # 15
                concealed(1, 12.0),         # +35 = 50 < 60
                leave(1, "r1", "rayon", 20.0, duration=20.0),  # +30 = 80 ≥ 60
            ],
        )
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision.rule == RULE_DISSIMULATION
        assert decision.severity == "high"
        assert decision.score == 80.0
        assert decision.track_id == 1
        stages = [e["stage"] for e in decision.evidence]
        assert stages == ["grab", "conceal", "left_shelf_after_conceal"]

    def test_grab_alone_is_not_enough(self):
        engine = RulesEngine()
        assert run(engine, [grabbed(1, 0.0)]) == []

    def test_conceal_without_grab_scores_less(self):
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                enter(1, "r1", "rayon", 0.0),
                concealed(1, 10.0),  # 20 (pas de saisie vue)
                leave(1, "r1", "rayon", 15.0, duration=15.0),  # +30 = 50 < 60
            ],
        )
        assert decisions == []

    def test_old_findings_expire(self):
        engine = RulesEngine(RulesConfig(window_seconds=60.0))
        decisions = run(
            engine,
            [
                enter(1, "r1", "rayon", 0.0),
                grabbed(1, 0.0),
                concealed(1, 5.0),
                # La sortie du rayon arrive bien après la fenêtre : tout a expiré.
                leave(1, "r1", "rayon", 300.0, duration=300.0),
            ],
        )
        assert decisions == []

    def test_gesture_boosts_concealment(self):
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                grabbed(1, 0.0),      # 15
                concealed(1, 5.0),    # +35 = 50
                gesture(1, 6.0),      # +15 = 65 ≥ 60
            ],
        )
        assert len(decisions) == 1
        assert decisions[0].rule == RULE_DISSIMULATION

    def test_gesture_alone_never_alerts(self):
        # SPEC §6 règle 4 : jamais seul.
        engine = RulesEngine(RulesConfig(alert_threshold=10.0))
        decisions = run(engine, [gesture(1, 0.0), gesture(1, 5.0), gesture(1, 9.0)])
        assert decisions == []


class TestCheckoutBypass:
    def test_exit_without_checkout(self):
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                enter(1, "r1", "rayon", 0.0),
                leave(1, "r1", "rayon", 30.0, duration=30.0),
                enter(1, "s1", "sortie", 35.0),
            ],
        )
        assert len(decisions) == 1
        assert decisions[0].rule == RULE_PASSAGE_SANS_CAISSE
        assert decisions[0].severity == "medium"
        assert decisions[0].evidence[0]["shelf_seconds"] == 30.0

    def test_checkout_passage_prevents_alert(self):
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                enter(1, "r1", "rayon", 0.0),
                leave(1, "r1", "rayon", 30.0, duration=30.0),
                enter(1, "c1", "caisse", 31.0),
                leave(1, "c1", "caisse", 45.0, duration=14.0),
                enter(1, "s1", "sortie", 50.0),
            ],
        )
        assert decisions == []

    def test_short_visit_does_not_trigger(self):
        # Moins de min_shelf_seconds en rayon : simple passage, pas de signal.
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                enter(1, "r1", "rayon", 0.0),
                leave(1, "r1", "rayon", 5.0, duration=5.0),
                enter(1, "s1", "sortie", 6.0),
            ],
        )
        assert decisions == []

    def test_ongoing_shelf_time_counts(self):
        # Toujours « dans » le rayon au moment d'entrer en sortie (zones qui se chevauchent).
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                enter(1, "r1", "rayon", 0.0),
                enter(1, "s1", "sortie", 20.0),
            ],
        )
        assert len(decisions) == 1
        assert decisions[0].rule == RULE_PASSAGE_SANS_CAISSE


class TestAbnormalDwell:
    def test_low_motion_dwell_in_shelf_zone(self):
        engine = RulesEngine(RulesConfig(alert_threshold=40.0))
        decisions = run(engine, [dwell(1, "rayon", 60.0, radius=0.02)])
        assert len(decisions) == 1
        assert decisions[0].rule == RULE_TEMPS_ANORMAL
        assert decisions[0].severity == "low"

    def test_moving_person_does_not_trigger(self):
        engine = RulesEngine(RulesConfig(alert_threshold=40.0))
        assert run(engine, [dwell(1, "rayon", 60.0, radius=0.3)]) == []

    def test_non_sensitive_zone_ignored(self):
        engine = RulesEngine(RulesConfig(alert_threshold=40.0))
        assert run(engine, [dwell(1, "caisse", 60.0, radius=0.01)]) == []

    def test_unknown_radius_ignored(self):
        engine = RulesEngine(RulesConfig(alert_threshold=40.0))
        assert run(engine, [dwell(1, "rayon", 60.0, radius=None)]) == []


class TestForbiddenZone:
    def test_reserve_entry_alerts(self):
        engine = RulesEngine()
        decisions = run(engine, [enter(1, "res", "reserve", 0.0)])
        assert len(decisions) == 1
        assert decisions[0].rule == RULE_ZONE_INTERDITE
        assert decisions[0].severity == "high"


class TestEngineBehavior:
    def test_cooldown_prevents_spam(self):
        engine = RulesEngine(RulesConfig(cooldown_seconds=60.0))
        first = run(engine, [enter(1, "res", "reserve", 0.0)])
        assert len(first) == 1
        # Ré-entrée immédiate : indices frais mais cooldown actif.
        again = run(
            engine,
            [leave(1, "res", "reserve", 5.0, 5.0), enter(1, "res", "reserve", 10.0)],
        )
        assert again == []
        # Après le cooldown, une nouvelle alerte est possible.
        later = run(
            engine,
            [leave(1, "res", "reserve", 15.0, 5.0), enter(1, "res", "reserve", 100.0)],
        )
        assert len(later) == 1

    def test_tracks_are_independent(self):
        engine = RulesEngine()
        decisions = run(
            engine,
            [
                grabbed(1, 0.0),
                concealed(1, 5.0),
                # Le track 2 sort du rayon, pas le track 1 : personne ne franchit le seuil.
                enter(2, "r1", "rayon", 6.0),
                leave(2, "r1", "rayon", 20.0, duration=14.0),
            ],
        )
        assert decisions == []

    def test_alert_resets_findings(self):
        engine = RulesEngine()
        run(engine, [grabbed(1, 0.0), concealed(1, 5.0), gesture(1, 6.0)])
        # Après l'alerte : un seul nouvel indice ne suffit plus (état remis à zéro),
        # même une fois le cooldown passé.
        decisions = run(engine, [concealed(1, 200.0)])
        assert decisions == []

    def test_stale_tracks_are_pruned(self):
        engine = RulesEngine(RulesConfig(state_ttl_seconds=100.0))
        run(engine, [grabbed(1, 0.0)])
        run(engine, [enter(2, "r1", "rayon", 500.0)])
        assert 1 not in engine._tracks
        assert 2 in engine._tracks

    def test_event_without_track_or_ts_is_ignored(self):
        engine = RulesEngine()
        assert engine.process({"type": "object_grabbed", "ts": 1.0}) == []
        assert engine.process({"type": "object_grabbed", "track_id": 1}) == []


class TestConfig:
    def test_from_dict_overrides_and_ignores_unknown(self):
        config = RulesConfig.from_dict(
            {"alert_threshold": 42.0, "unknown_key": 1, "min_shelf_seconds": 3.0}
        )
        assert config.alert_threshold == 42.0
        assert config.min_shelf_seconds == 3.0
        assert config.cooldown_seconds == RulesConfig().cooldown_seconds

    def test_from_dict_none_gives_defaults(self):
        assert RulesConfig.from_dict(None) == RulesConfig()

    def test_per_camera_threshold_changes_decision(self):
        # Avec un seuil bas, la séquence saisie + dissimulation suffit.
        engine = RulesEngine(RulesConfig.from_dict({"alert_threshold": 50.0}))
        decisions = run(engine, [grabbed(1, 0.0), concealed(1, 5.0)])
        assert len(decisions) == 1

    def test_update_config_applies_live(self):
        engine = RulesEngine()
        assert run(engine, [grabbed(1, 0.0), concealed(1, 5.0)]) == []
        engine.update_config(RulesConfig(alert_threshold=10.0))
        decisions = run(engine, [gesture(1, 6.0)])  # +15 → total 65 ≥ 10
        assert len(decisions) == 1
