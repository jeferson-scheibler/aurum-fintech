#!/bin/bash
set -e

sudo docker compose -f docker-compose.jenkins.yml up -d --build
echo ""
echo "Jenkins disponivel em: http://177.44.248.105:8090"
echo ""
echo "Senha inicial de admin:"
sudo docker exec aurum_jenkins cat /var/jenkins_home/secrets/initialAdminPassword
echo ""
