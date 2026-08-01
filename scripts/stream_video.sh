#!/bin/sh
# Pousse un fichier vidéo local en boucle vers le serveur RTSP de test, pour
# tester la détection avec des personnes à l'image.
#
# N'utiliser que des vidéos libres de droits (ex. Pexels/Pixabay) ou générées —
# jamais de vraies images de clients (voir SPEC.md §8).
#
# Usage :
#   ./scripts/stream_video.sh chemin/vers/video.mp4 [url_rtsp]
# Par défaut l'URL est rtsp://localhost:8554/teststream (mediamtx du compose).
set -e

VIDEO="$1"
TARGET="${2:-rtsp://localhost:8554/teststream}"

if [ -z "$VIDEO" ] || [ ! -f "$VIDEO" ]; then
  echo "usage: $0 <video.mp4> [rtsp://host:8554/path]" >&2
  exit 1
fi

exec ffmpeg -re -stream_loop -1 -i "$VIDEO" \
  -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -g 50 -an \
  -f rtsp -rtsp_transport tcp "$TARGET"
