#!/bin/bash
set -e

docker compose -f docker-compose.homolog.yml up -d --build
echo "Homolog atualizado: http://177.44.248.105:8081"
