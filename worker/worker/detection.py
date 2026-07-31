"""Détection de personnes YOLOv8 + tracking ByteTrack (via Ultralytics).

RGPD : aucune reconnaissance faciale, aucune identification. Les IDs de
tracking viennent de ByteTrack, vivent en mémoire du processus et ne sont
jamais recoupés entre sessions, jours ou magasins.
"""

import logging

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0


class PersonDetector:
    def __init__(self, model_name: str = "yolov8n.pt"):
        # Import différé : les tests unitaires du worker n'ont pas besoin de torch.
        from ultralytics import YOLO

        self._model = YOLO(model_name)
        logger.info("YOLO model loaded: %s", model_name)

    def track(self, frame) -> list[tuple[int, float, float]]:
        """Détecte et tracke les personnes d'une frame BGR.

        Retourne [(track_id, x, y)] avec (x, y) le point au sol (centre-bas de
        la bounding box) en coordonnées normalisées [0,1].
        """
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
        detections = []
        for (x1, y1, x2, y2), track_id in zip(
            boxes.xyxy.tolist(), boxes.id.int().tolist()
        ):
            foot_x = ((x1 + x2) / 2) / width
            foot_y = y2 / height
            detections.append((int(track_id), foot_x, foot_y))
        return detections
