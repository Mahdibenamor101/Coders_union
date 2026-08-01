"""Superviseur multi-caméras : un processus worker par flux, orchestré.

Interroge l'API périodiquement et maintient un sous-processus `worker.main`
par caméra enregistrée : démarrage des nouvelles, arrêt des supprimées,
redémarrage (avec backoff) de celles qui tombent. C'est l'entrée par défaut
du conteneur worker — plus besoin de WORKER_CAMERA_ID.

`WORKER_CAMERA_ID` reste supporté comme filtre (mode mono-caméra).
"""

import logging
import os
import signal
import subprocess
import sys
import time

import requests

logger = logging.getLogger("supervisor")

POLL_INTERVAL_SECONDS = 30.0
RESTART_BACKOFF_SECONDS = 10.0


def reconcile(desired: set[str], running: set[str]) -> tuple[set[str], set[str]]:
    """Retourne (à démarrer, à arrêter) — logique pure, testée unitairement."""
    return desired - running, running - desired


def fetch_camera_ids(api_url: str, api_key: str) -> set[str] | None:
    """IDs de caméras connus de l'API, ou None si l'API est injoignable."""
    try:
        response = requests.get(
            f"{api_url}/internal/cameras",
            headers={"X-API-Key": api_key},
            timeout=10,
        )
        response.raise_for_status()
        return {camera["id"] for camera in response.json()}
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("could not list cameras (%s)", exc)
        return None


class Supervisor:
    def __init__(self, api_url: str, api_key: str, only_camera: str = ""):
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._only_camera = only_camera
        self._processes: dict[str, subprocess.Popen] = {}
        self._last_exit: dict[str, float] = {}
        self._stop = False

    def run(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

        logger.info("supervisor started (poll every %.0fs)", POLL_INTERVAL_SECONDS)
        while not self._stop:
            self._tick()
            deadline = time.time() + POLL_INTERVAL_SECONDS
            while not self._stop and time.time() < deadline:
                time.sleep(1)
        self._shutdown()

    def _tick(self) -> None:
        desired = fetch_camera_ids(self._api_url, self._api_key)
        if desired is None:
            return  # API injoignable : on garde les workers en l'état
        if self._only_camera:
            desired &= {self._only_camera}

        self._reap()
        to_start, to_stop = reconcile(desired, set(self._processes))

        for camera_id in to_stop:
            logger.info("camera %s removed, stopping its worker", camera_id)
            self._terminate(camera_id)
        for camera_id in to_start:
            # Backoff après un crash pour ne pas boucler à chaud.
            if time.time() - self._last_exit.get(camera_id, 0) < RESTART_BACKOFF_SECONDS:
                continue
            self._spawn(camera_id)

    def _spawn(self, camera_id: str) -> None:
        env = {**os.environ, "CAMERA_ID": camera_id}
        process = subprocess.Popen([sys.executable, "-m", "worker.main"], env=env)
        self._processes[camera_id] = process
        logger.info("worker started for camera %s (pid %d)", camera_id, process.pid)

    def _reap(self) -> None:
        for camera_id, process in list(self._processes.items()):
            if process.poll() is not None:
                logger.warning(
                    "worker for camera %s exited with code %s",
                    camera_id,
                    process.returncode,
                )
                self._last_exit[camera_id] = time.time()
                del self._processes[camera_id]

    def _terminate(self, camera_id: str) -> None:
        process = self._processes.pop(camera_id, None)
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    def _handle_signal(self, *_args) -> None:
        self._stop = True

    def _shutdown(self) -> None:
        logger.info("supervisor shutting down (%d workers)", len(self._processes))
        for camera_id in list(self._processes):
            self._terminate(camera_id)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    api_url = os.environ.get("API_URL", "http://api:8000")
    api_key = os.environ.get("API_KEY", "")
    if not api_key:
        raise RuntimeError("missing required environment variable: API_KEY")
    Supervisor(api_url, api_key, os.environ.get("WORKER_CAMERA_ID", "")).run()


if __name__ == "__main__":
    main()
