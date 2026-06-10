#!/bin/bash
set -e

REPO_URL="https://github.com/jeferson-scheibler/aurum-fintech.git"
# Path fixo para bater com os volumes do docker-compose.jenkins.yml e do Jenkinsfile.
PROJETO="/home/univates/aurum-fintech"
PARENT_DIR="$(dirname "$PROJETO")"

separador() { echo ""; echo "──────────────────────────────────────────"; echo "  $1"; echo "──────────────────────────────────────────"; }

# ── 1. dependências base ────────────────────────────────────────────────────────
separador "Instalando dependências base"
sudo apt-get update -qq
sudo apt-get install -y ca-certificates curl git

# ── 2. Docker Engine ────────────────────────────────────────────────────────────
separador "Instalando Docker"
if command -v docker &> /dev/null; then
    echo "Docker já instalado, pulando..."
else
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    sudo systemctl enable docker
    sudo systemctl start docker
    echo "Docker instalado com sucesso."
fi

# ── 3. projeto ──────────────────────────────────────────────────────────────────
separador "Clonando o projeto em $PROJETO"
sudo mkdir -p "$PARENT_DIR"
sudo chown -R "$USER":"$USER" "$PARENT_DIR"

if [ -d "$PROJETO" ]; then
    echo "Projeto já existe, atualizando..."
    git -C "$PROJETO" pull
else
    git clone "$REPO_URL" "$PROJETO"
fi

cd "$PROJETO"

# ── 3.1 .env ────────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo ""
        echo "⚠  .env criado a partir de .env.example com valores padrao."
        echo "   Edite $PROJETO/.env e ajuste SECRET_KEY/DB_PASS/JENKINS_ADMIN_PASSWORD antes de algo serio."
        echo ""
    fi
fi

# ── 4. Jenkins ──────────────────────────────────────────────────────────────────
separador "Subindo Jenkins"
sudo docker compose -f docker-compose.jenkins.yml up -d --build

echo "Aguardando Jenkins inicializar..."
until sudo docker exec aurum_jenkins curl -s http://localhost:8080/login &>/dev/null; do
    sleep 3
    printf "."
done
echo ""

# ── 5. resultado ────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')

separador "Pronto!"
echo ""
echo "  Jenkins:  http://$IP:8090"
echo "  Login:    admin"
echo "  Senha:    (definida em JENKINS_ADMIN_PASSWORD no .env)"
echo ""
echo "  O job 'Deploy Aurum' já está criado e pronto para uso."
echo "  Acesse o Jenkins e clique em 'Build with Parameters'."
echo ""
