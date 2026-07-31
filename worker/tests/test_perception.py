from worker.perception import (
    GestureMonitor,
    MovementTracker,
    ObjectAssociationTracker,
    PersonObs,
)


def person(tid=1, wrist=(0.5, 0.5)):
    return PersonObs(
        track_id=tid,
        foot=(0.5, 0.9),
        bbox=(0.4, 0.2, 0.6, 0.9),
        wrists=(wrist,) if wrist else (),
    )


def bottle_at(x, y, size=0.02):
    return ("bottle", (x - size, y - size, x + size, y + size))


class TestObjectAssociation:
    def test_grab_requires_stable_hold(self):
        tracker = ObjectAssociationTracker(min_hold_updates=3)
        p = person()
        near = bottle_at(0.5, 0.5)

        assert tracker.update(1.0, [p], [near]) == []
        assert tracker.update(2.0, [p], [near]) == []
        events = tracker.update(3.0, [p], [near])
        assert [e["type"] for e in events] == ["object_grabbed"]
        assert events[0]["object_class"] == "bottle"
        # Pas de doublon.
        assert tracker.update(4.0, [p], [near]) == []

    def test_far_object_is_not_grabbed(self):
        tracker = ObjectAssociationTracker(min_hold_updates=2, hand_radius=0.08)
        p = person()
        far = bottle_at(0.9, 0.1)
        for ts in range(1, 6):
            assert tracker.update(float(ts), [p], [far]) == []

    def test_conceal_after_disappearance(self):
        tracker = ObjectAssociationTracker(min_hold_updates=2, conceal_updates=3)
        p = person()
        near = bottle_at(0.5, 0.5)
        tracker.update(1.0, [p], [near])
        tracker.update(2.0, [p], [near])  # object_grabbed

        assert tracker.update(3.0, [p], []) == []
        assert tracker.update(4.0, [p], []) == []
        events = tracker.update(5.0, [p], [])
        assert [e["type"] for e in events] == ["object_concealed"]

    def test_reappearance_resets_conceal_counter(self):
        tracker = ObjectAssociationTracker(min_hold_updates=2, conceal_updates=3)
        p = person()
        near = bottle_at(0.5, 0.5)
        tracker.update(1.0, [p], [near])
        tracker.update(2.0, [p], [near])

        tracker.update(3.0, [p], [])
        tracker.update(4.0, [p], [near])  # réapparu : compteur remis à zéro
        assert tracker.update(5.0, [p], []) == []
        assert tracker.update(6.0, [p], []) == []
        events = tracker.update(7.0, [p], [])
        assert [e["type"] for e in events] == ["object_concealed"]

    def test_bbox_fallback_without_pose(self):
        tracker = ObjectAssociationTracker(min_hold_updates=2)
        p = person(wrist=None)  # pas de keypoints
        inside = bottle_at(0.5, 0.5)
        tracker.update(1.0, [p], [inside])
        events = tracker.update(2.0, [p], [inside])
        assert [e["type"] for e in events] == ["object_grabbed"]

    def test_vanished_person_state_is_dropped(self):
        tracker = ObjectAssociationTracker(min_hold_updates=2, person_ttl=5.0)
        p = person()
        near = bottle_at(0.5, 0.5)
        tracker.update(1.0, [p], [near])
        tracker.update(2.0, [p], [near])
        # La personne disparaît au-delà du TTL : plus jamais de conceal pour elle.
        assert tracker.update(20.0, [], []) == []
        assert tracker.update(21.0, [person(tid=2)], []) == []


class TestGestureMonitor:
    def test_alternating_head_turns_emit_event(self):
        monitor = GestureMonitor(min_amplitude=0.3, min_changes=3, window_seconds=10.0)
        sequence = [(1.0, -0.5), (2.0, 0.5), (3.0, -0.5), (4.0, 0.5)]
        events = [monitor.update(ts, 1, d) for ts, d in sequence]
        assert events[:3] == [None, None, None]
        assert events[3]["type"] == "surveillance_gesture"
        assert events[3]["count"] == 3

    def test_static_head_never_emits(self):
        monitor = GestureMonitor()
        for ts in range(20):
            assert monitor.update(float(ts), 1, 0.5) is None

    def test_small_movements_ignored(self):
        monitor = GestureMonitor(min_amplitude=0.3)
        for ts, d in enumerate([-0.1, 0.1, -0.1, 0.1, -0.1, 0.1]):
            assert monitor.update(float(ts), 1, d) is None

    def test_changes_outside_window_expire(self):
        monitor = GestureMonitor(min_changes=3, window_seconds=10.0)
        assert monitor.update(0.0, 1, -0.5) is None
        assert monitor.update(1.0, 1, 0.5) is None
        assert monitor.update(2.0, 1, -0.5) is None
        # Troisième alternance trop tard : les premières ont expiré.
        assert monitor.update(50.0, 1, 0.5) is None

    def test_none_head_dir_is_ignored(self):
        monitor = GestureMonitor()
        assert monitor.update(1.0, 1, None) is None


class TestMovementTracker:
    def test_radius_of_static_person_is_small(self):
        tracker = MovementTracker()
        for ts in range(10):
            tracker.add(float(ts), 1, 0.5, 0.5)
        assert tracker.radius(1) == 0.0

    def test_radius_of_moving_person(self):
        tracker = MovementTracker()
        tracker.add(0.0, 1, 0.0, 0.5)
        tracker.add(1.0, 1, 1.0, 0.5)
        assert tracker.radius(1) == 0.5

    def test_old_points_fall_out_of_window(self):
        tracker = MovementTracker(window_seconds=10.0)
        tracker.add(0.0, 1, 0.0, 0.0)
        tracker.add(100.0, 1, 0.5, 0.5)
        tracker.add(101.0, 1, 0.5, 0.5)
        assert tracker.radius(1) == 0.0

    def test_unknown_track_returns_none(self):
        assert MovementTracker().radius(42) is None
