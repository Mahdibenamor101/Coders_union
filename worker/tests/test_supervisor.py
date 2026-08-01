from worker.supervisor import fetch_camera_ids, reconcile


class TestReconcile:
    def test_start_new_cameras(self):
        to_start, to_stop = reconcile({"a", "b"}, set())
        assert to_start == {"a", "b"}
        assert to_stop == set()

    def test_stop_removed_cameras(self):
        to_start, to_stop = reconcile({"a"}, {"a", "b"})
        assert to_start == set()
        assert to_stop == {"b"}

    def test_steady_state(self):
        assert reconcile({"a"}, {"a"}) == (set(), set())


class TestFetchCameraIds:
    def test_unreachable_api_returns_none(self, monkeypatch):
        import requests

        def boom(*args, **kwargs):
            raise requests.ConnectionError("down")

        monkeypatch.setattr("worker.supervisor.requests.get", boom)
        # None (et pas set vide) : on ne tue pas les workers quand l'API tombe.
        assert fetch_camera_ids("http://api", "key") is None

    def test_parses_ids(self, monkeypatch):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return [{"id": "cam1", "name": "A"}, {"id": "cam2", "name": "B"}]

        monkeypatch.setattr(
            "worker.supervisor.requests.get", lambda *a, **k: Response()
        )
        assert fetch_camera_ids("http://api", "key") == {"cam1", "cam2"}
