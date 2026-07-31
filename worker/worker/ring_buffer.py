import threading
from collections import deque


class FrameRingBuffer:
    """Buffer circulaire de frames JPEG horodatées, borné en durée.

    RGPD : c'est la seule rétention du flux brut — au-delà de `max_seconds`,
    les frames sont écrasées. Rien n'est écrit sur disque ni en base.
    """

    def __init__(self, max_seconds: float, fps: float):
        capacity = max(1, int(max_seconds * fps))
        self._frames: deque[tuple[float, bytes]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, timestamp: float, jpeg: bytes) -> None:
        with self._lock:
            self._frames.append((timestamp, jpeg))

    def snapshot(self, start_ts: float, end_ts: float) -> list[tuple[float, bytes]]:
        """Copie des frames dont le timestamp est dans [start_ts, end_ts]."""
        with self._lock:
            return [f for f in self._frames if start_ts <= f[0] <= end_ts]

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)

    @property
    def oldest_ts(self) -> float | None:
        with self._lock:
            return self._frames[0][0] if self._frames else None

    @property
    def newest_ts(self) -> float | None:
        with self._lock:
            return self._frames[-1][0] if self._frames else None
