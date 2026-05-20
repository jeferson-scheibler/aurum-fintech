#!/bin/bash
set -e

docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
echo "Prod atualizado: http://177.44.248.105:8082"
