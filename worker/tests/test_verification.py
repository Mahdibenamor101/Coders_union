import json
from types import SimpleNamespace

from worker.verification import (
    MultimodalVerifier,
    apply_assessment,
    select_key_frames,
)


def frames(count):
    return [(float(i), f"jpeg-{i}".encode()) for i in range(count)]


class TestSelectKeyFrames:
    def test_empty(self):
        assert select_key_frames([]) == []

    def test_fewer_than_max_returns_all(self):
        assert select_key_frames(frames(3)) == [b"jpeg-0", b"jpeg-1", b"jpeg-2"]

    def test_samples_evenly_including_ends(self):
        selected = select_key_frames(frames(100), max_frames=4)
        assert len(selected) == 4
        assert selected[0] == b"jpeg-0"
        assert selected[-1] == b"jpeg-99"


class TestApplyAssessment:
    ALERT = {"rule": "dissimulation", "severity": "high", "score": 80.0, "evidence": []}

    def test_none_assessment_is_identity(self):
        assert apply_assessment(self.ALERT, None) == self.ALERT

    def test_confirmed_keeps_score(self):
        adjusted = apply_assessment(
            self.ALERT, {"verdict": "oui", "factor": 1.0, "description": "…"}
        )
        assert adjusted["score"] == 80.0
        assert adjusted["severity"] == "high"
        assert adjusted["evidence"][-1]["stage"] == "multimodal_verification"

    def test_negative_verdict_halves_score_and_lowers_severity(self):
        adjusted = apply_assessment(
            self.ALERT,
            {"verdict": "non", "factor": 0.5, "description": "rien de visible"},
        )
        assert adjusted["score"] == 40.0
        assert adjusted["severity"] == "low"
        # L'alerte n'est jamais supprimée : l'humain décide.
        assert adjusted["rule"] == "dissimulation"

    def test_original_alert_not_mutated(self):
        alert = dict(self.ALERT)
        apply_assessment(alert, {"verdict": "non", "factor": 0.5, "description": "x"})
        assert alert["score"] == 80.0
        assert alert["evidence"] == []


class FakeAnthropicClient:
    def __init__(self, response):
        self._response = response
        self.requests = []

    @property
    def messages(self):
        outer = self

        class Messages:
            def create(self, **kwargs):
                outer.requests.append(kwargs)
                return outer._response

        return Messages()


def make_response(payload, stop_reason="end_turn"):
    blocks = [SimpleNamespace(type="text", text=json.dumps(payload))]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks, stop_details=None)


class TestMultimodalVerifier:
    def test_assess_parses_structured_response(self):
        client = FakeAnthropicClient(
            make_response({"description": "Une personne repose l'article.",
                           "sequence_visible": "non"})
        )
        verifier = MultimodalVerifier(client=client)
        result = verifier.assess(frames(10), "dissimulation")
        assert result == {
            "verdict": "non",
            "factor": 0.5,
            "description": "Une personne repose l'article.",
        }
        # Frames clés limitées et prompt factuel sans identification.
        request = client.requests[0]
        images = [b for b in request["messages"][0]["content"] if b["type"] == "image"]
        assert len(images) == 4
        assert "identifier" in request["system"] or "identifie" in request["system"]

    def test_refusal_returns_none(self):
        client = FakeAnthropicClient(make_response({}, stop_reason="refusal"))
        verifier = MultimodalVerifier(client=client)
        assert verifier.assess(frames(5), "dissimulation") is None

    def test_api_error_returns_none(self):
        class BoomClient:
            @property
            def messages(self):
                class Messages:
                    def create(self, **kwargs):
                        raise RuntimeError("api down")

                return Messages()

        verifier = MultimodalVerifier(client=BoomClient())
        assert verifier.assess(frames(5), "dissimulation") is None

    def test_no_frames_returns_none_without_call(self):
        client = FakeAnthropicClient(make_response({}))
        verifier = MultimodalVerifier(client=client)
        assert verifier.assess([], "dissimulation") is None
        assert client.requests == []
