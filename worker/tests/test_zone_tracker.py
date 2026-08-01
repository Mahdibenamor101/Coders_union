from worker.zone_tracker import Zone, ZoneTracker, point_in_polygon

UNIT_SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


def make_zone(zone_id="z1", zone_type="rayon", polygon=None):
    # Par défaut : quart supérieur gauche de l'image.
    polygon = polygon or ((0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5))
    return Zone(id=zone_id, name=f"Zone {zone_id}", type=zone_type, polygon=polygon)


class TestPointInPolygon:
    def test_inside_and_outside(self):
        assert point_in_polygon(0.5, 0.5, UNIT_SQUARE)
        assert not point_in_polygon(1.5, 0.5, UNIT_SQUARE)
        assert not point_in_polygon(-0.1, 0.5, UNIT_SQUARE)

    def test_triangle(self):
        triangle = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
        assert point_in_polygon(0.2, 0.2, triangle)
        assert not point_in_polygon(0.8, 0.8, triangle)

    def test_concave_polygon(self):
        # Polygone en « L » : le creux n'est pas dedans.
        concave = ((0.0, 0.0), (1.0, 0.0), (1.0, 0.4), (0.4, 0.4), (0.4, 1.0), (0.0, 1.0))
        assert point_in_polygon(0.2, 0.8, concave)
        assert not point_in_polygon(0.8, 0.8, concave)


class TestZoneTracker:
    def test_enter_then_leave(self):
        tracker = ZoneTracker([make_zone()])

        events = tracker.process(10.0, [(1, 0.25, 0.25)])
        assert [e["type"] for e in events] == ["person_entered_zone"]
        assert events[0]["track_id"] == 1
        assert events[0]["zone_id"] == "z1"
        assert events[0]["zone_type"] == "rayon"

        # Toujours dedans : pas de nouvel événement.
        assert tracker.process(11.0, [(1, 0.3, 0.3)]) == []

        events = tracker.process(15.0, [(1, 0.9, 0.9)])
        assert [e["type"] for e in events] == ["person_left_zone"]
        assert events[0]["duration_seconds"] == 5.0

    def test_dwell_emitted_once_after_threshold(self):
        tracker = ZoneTracker([make_zone()], dwell_seconds=30.0)
        tracker.process(0.0, [(1, 0.25, 0.25)])

        assert tracker.process(29.0, [(1, 0.25, 0.25)]) == []
        events = tracker.process(31.0, [(1, 0.25, 0.25)])
        assert [e["type"] for e in events] == ["person_dwell"]
        assert events[0]["dwell_seconds"] == 31.0
        # Une seule fois par (track, zone).
        assert tracker.process(60.0, [(1, 0.25, 0.25)]) == []

    def test_lost_track_expires_and_leaves_zones(self):
        tracker = ZoneTracker([make_zone()], track_ttl=5.0)
        tracker.process(0.0, [(1, 0.25, 0.25)])

        # Le track 1 disparaît ; un autre track maintient le pipeline actif.
        assert tracker.process(3.0, [(2, 0.9, 0.9)]) == []
        events = tracker.process(6.0, [(2, 0.9, 0.9)])
        assert [(e["type"], e["track_id"]) for e in events] == [
            ("person_left_zone", 1)
        ]
        assert events[0]["duration_seconds"] == 6.0

        # IDs éphémères : l'état du track 1 est oublié, une réapparition ré-entre.
        events = tracker.process(7.0, [(1, 0.25, 0.25)])
        assert [e["type"] for e in events] == ["person_entered_zone"]

    def test_multiple_zones_and_tracks(self):
        left = make_zone("left", polygon=((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)))
        top = make_zone("top", zone_type="caisse", polygon=((0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)))
        tracker = ZoneTracker([left, top])

        # Track 1 dans l'intersection (2 entrées), track 2 hors zones.
        events = tracker.process(0.0, [(1, 0.25, 0.25), (2, 0.9, 0.9)])
        assert sorted((e["type"], e["zone_id"]) for e in events) == [
            ("person_entered_zone", "left"),
            ("person_entered_zone", "top"),
        ]

        # Track 1 descend : quitte "top", reste dans "left".
        events = tracker.process(2.0, [(1, 0.25, 0.75), (2, 0.9, 0.9)])
        assert [(e["type"], e["zone_id"]) for e in events] == [
            ("person_left_zone", "top")
        ]

    def test_update_zones_drops_removed_zone_state(self):
        tracker = ZoneTracker([make_zone("z1")])
        tracker.process(0.0, [(1, 0.25, 0.25)])

        tracker.update_zones([make_zone("z2", polygon=((0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.5, 1.0)))])
        # z1 n'existe plus : aucun événement de sortie orphelin, entrée dans z2 seulement.
        events = tracker.process(1.0, [(1, 0.75, 0.75)])
        assert [(e["type"], e["zone_id"]) for e in events] == [
            ("person_entered_zone", "z2")
        ]

    def test_no_zones_no_events(self):
        tracker = ZoneTracker([])
        assert tracker.process(0.0, [(1, 0.5, 0.5)]) == []
