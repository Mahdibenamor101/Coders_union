#!/bin/sh
# Pousse une mire vidéo générée (aucune image réelle) vers le serveur RTSP de test.
# Le flux est disponible sur rtsp://mediamtx:8554/teststream dans le réseau Docker.
set -e

# Petit délai pour laisser mediamtx démarrer.
sleep 2

exec ffmpeg -re \
  -f lavfi -i "testsrc2=size=1280x720:rate=25" \
  -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -g 50 \
  -f rtsp -rtsp_transport tcp rtsp://mediamtx:8554/teststream
