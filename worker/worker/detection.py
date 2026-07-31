"""Détection de personnes (pose) et d'objets — YOLOv8 + ByteTrack via Ultralytics.

RGPD : aucune reconnaissance faciale, aucune identification. Les IDs de
tracking viennent de ByteTrack, vivent en mémoire du processus et ne sont
jamais recoupés entre sessions, jours ou magasins. Les keypoints de pose ne
servent qu'à des heuristiques géométriques (mains, direction de tête) et ne
sont jamais persistés.
"""

import logging

from .perception import PersonObs

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0
KEYPOINT_CONFIDENCE = 0.3
# Indices COCO des keypoints utilisés.
KP_NOSE, KP_L_SHOULDER, KP_R_SHOULDER, KP_L_WRIST, KP_R_WRIST = 0, 5, 6, 9, 10


class PersonDetector:
    """Détection + tracking de personnes ; keypoints si le modèle est un modèle pose."""

    def __init__(self, model_name: str = "yolov8n-pose.pt"):
        # Import différé : les tests unitaires du worker n'ont pas besoin de torch.
        from ultralytics import YOLO

        self._model = YOLO(model_name)
        logger.info("YOLO person model loaded: %s", model_name)

    def track(self, frame) -> list[PersonObs]:
        results = self._model.track(
            frame,
            persist=True,
            classes=[PERSON_CLASS_ID],
            tracker="bytetrack.yaml",
            verbose=False,
        )
        result = results[0]
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return []

        height, width = frame.shape[:2]
        keypoints = None
        if getattr(result, "keypoints", None) is not None and result.keypoints.xy is not None:
            keypoints = result.keypoints

        observations = []
        for index, ((x1, y1, x2, y2), track_id) in enumerate(
            zip(boxes.xyxy.tolist(), boxes.id.int().tolist())
        ):
            bbox = (x1 / width, y1 / height, x2 / width, y2 / height)
            foot = (((x1 + x2) / 2) / width, y2 / height)
            wrists, head_dir = self._pose_features(keypoints, index, width, height)
            observations.append(
                PersonObs(
                    track_id=int(track_id),
                    foot=foot,
                    bbox=bbox,
                    wrists=wrists,
                    head_dir=head_dir,
                )
            )
        return observations

    def _pose_features(self, keypoints, index, width, height):
        if keypoints is None:
            return (), None
        try:
            xy = keypoints.xy[index].tolist()
            conf = (
                keypoints.conf[index].tolist()
                if keypoints.conf is not None
                else [1.0] * len(xy)
            )
        except (IndexError, TypeError):
            return (), None

        def point(kp_index):
            if kp_index >= len(xy) or conf[kp_index] < KEYPOINT_CONFIDENCE:
                return None
            x, y = xy[kp_index]
            if x == 0 and y == 0:
                return None
            return (x / width, y / height)

        wrists = tuple(p for p in (point(KP_L_WRIST), point(KP_R_WRIST)) if p)

        head_dir = None
        nose = point(KP_NOSE)
        left_shoulder = point(KP_L_SHOULDER)
        right_shoulder = point(KP_R_SHOULDER)
        if nose and left_shoulder and right_shoulder:
            shoulder_cx = (left_shoulder[0] + right_shoulder[0]) / 2
            shoulder_width = abs(left_shoulder[0] - right_shoulder[0])
            if shoulder_width > 1e-3:
                head_dir = (nose[0] - shoulder_cx) / shoulder_width

        return wrists, head_dir


# Sous-ensemble COCO plausible en rayon de magasin.
DEFAULT_OBJECT_CLASSES = (
    "bottle",
    "cup",
    "wine glass",
    "book",
    "cell phone",
    "handbag",
    "backpack",
    "banana",
    "apple",
    "orange",
)


class ObjectDetector:
    """Détection d'objets « saisissables » (sans tracking, appelée 1 frame sur N)."""

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        class_names: tuple[str, ...] = DEFAULT_OBJECT_CLASSES,
        confidence: float = 0.35,
    ):
        from ultralytics import YOLO

        self._model = YOLO(model_name)
        self._confidence = confidence
        wanted = set(class_names)
        self._class_ids = [
            class_id
            for class_id, name in self._model.names.items()
            if name in wanted
        ]
        self._names = self._model.names
        logger.info(
            "YOLO object model loaded: %s (%d classes)", model_name, len(self._class_ids)
        )

    def detect(self, frame) -> list[tuple[str, tuple[float, float, float, float]]]:
        results = self._model.predict(
            frame, classes=self._class_ids, conf=self._confidence, verbose=False
        )
        result = results[0]
        if result.boxes is None:
            return []
        height, width = frame.shape[:2]
        detections = []
        for (x1, y1, x2, y2), class_id in zip(
            result.boxes.xyxy.tolist(), result.boxes.cls.int().tolist()
        ):
            detections.append(
                (
                    self._names[int(class_id)],
                    (x1 / width, y1 / height, x2 / width, y2 / height),
                )
            )
        return detections
