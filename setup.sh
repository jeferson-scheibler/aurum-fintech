#!/bin/bash
set -e

REPO_URL="https://github.com/jeferson-scheibler/aurum-fintech.git"
PROJETO="$HOME/aurum-fintech"

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
separador "Clonando o projeto"
if [ -d "$PROJETO" ]; then
    echo "Projeto já existe, atualizando..."
    git -C "$PROJETO" pull
else
    git clone "$REPO_URL" "$PROJETO"
fi

cd "$PROJETO"

# ── 4. Jenkins ──────────────────────────────────────────────────────────────────
separador "Subindo Jenkins"
sudo docker compose -f docker-compose.jenkins.yml up -d --build

echo "Aguardando Jenkins inicializar..."
until sudo docker exec aurum_jenkins test -f /var/jenkins_home/secrets/initialAdminPassword 2>/dev/null; do
    sleep 3
    printf "."
done
echo ""

# ── 5. resultado ────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
SENHA=$(sudo docker exec aurum_jenkins cat /var/jenkins_home/secrets/initialAdminPassword)

separador "Pronto!"
echo ""
echo "  Jenkins:  http://$IP:8080"
echo ""
echo "  Senha inicial:"
echo "  $SENHA"
echo ""
echo "  Próximos passos:"
echo "  1. Acesse o Jenkins e faça o setup inicial"
echo "  2. Crie um job Pipeline com o conteúdo do Jenkinsfile"
echo "  3. Use o job para subir homolog e prod"
echo ""
