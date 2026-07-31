FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Torch CPU d'abord (le worker GPU aura son propre Dockerfile plus tard) —
# évite de tirer les roues CUDA (~2 Go) via la dépendance d'ultralytics.
RUN pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-télécharge les poids YOLO dans l'image : pas d'accès réseau au démarrage.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); YOLO('yolov8n-pose.pt')"

COPY worker ./worker

CMD ["python", "-m", "worker.main"]
