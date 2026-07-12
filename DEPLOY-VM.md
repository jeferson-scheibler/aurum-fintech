# Deploy do Bagual numa VM própria (ao lado de outros sites)

Guia para rodar o Bagual numa VM que já hospeda outros sites atrás do Nginx,
usando Docker. Por enquanto acessível via `http://IP_DA_VM:PORTA` (HTTP puro);
a etapa de domínio + HTTPS fica documentada no fim.

> **Pré-requisitos:** acesso SSH à VM, Docker + plugin Compose instalados
> (`docker --version` e `docker compose version` devem responder).

---

## 1. Baixar o código na VM

```bash
ssh usuario@IP_DA_VM
git clone https://github.com/jeferson-scheibler/aurum-fintech.git bagual
cd bagual
```

> Se já usa um diretório padrão para os sites, clone lá dentro.

## 2. Configurar o `.env`

```bash
cp .env.vm.example .env
nano .env
```

Preencha:
- `SECRET_KEY` — gere na hora: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `DB_PASS` — uma senha forte para o Postgres
- `APP_PORT` — uma porta **livre**, diferente dos outros sites (ex.: `8083`)
- `SMTP_*` — só se quiser os e-mails de notificação (senão deixe vazio)

## 3. Subir os containers

```bash
docker compose -f docker-compose.vm.yml --env-file .env up -d --build
```

Isso sobe três containers: `bagual_db` (Postgres), `bagual_flyway` (aplica as
migrations e sai) e `bagual_app` (a aplicação, via gunicorn). O Postgres **não**
fica exposto ao host — só a app, na `APP_PORT`.

Verifique:
```bash
docker compose -f docker-compose.vm.yml ps
docker compose -f docker-compose.vm.yml logs -f app   # Ctrl+C para sair
```

## 4. Liberar a porta no firewall

```bash
sudo ufw allow 8083/tcp        # troque pela sua APP_PORT
```
> Se a VM for de um provedor de nuvem, libere a porta também no **security group /
> firewall do painel** do provedor.

## 5. Testar

No navegador: `http://IP_DA_VM:8083`
Login inicial: **admin / admin123**

---

## ⚠ Faça isto logo após subir

1. **Trocar a senha do admin.** O `admin/admin123` é público (está no repositório).
   Numa URL acessível pela internet, isso é um risco. Hoje **não há tela de troca
   de senha** — peça pro Claude adicionar essa funcionalidade, ou troque direto no
   banco. Para trocar pelo banco:
   ```bash
   # gere o hash da nova senha
   docker run --rm python:3.12-slim sh -c "pip -q install werkzeug && \
     python -c \"from werkzeug.security import generate_password_hash as g; print(g('SUA_NOVA_SENHA'))\""
   # aplique (cole o hash gerado no lugar de HASH)
   docker exec -it bagual_db psql -U fintech -d financas_db \
     -c \"UPDATE usuario SET senha='HASH' WHERE login='admin';\"
   ```

---

## Atualizar o app depois de novas mudanças

```bash
cd bagual
git pull
docker compose -f docker-compose.vm.yml --env-file .env up -d --build
```
As migrations novas são aplicadas automaticamente pelo Flyway a cada subida.

## Parar / remover

```bash
docker compose -f docker-compose.vm.yml down          # para (mantém o banco)
docker compose -f docker-compose.vm.yml down -v        # para E APAGA o banco
```

---

## Depois: domínio + HTTPS (destrava PWA, compartilhar comprovante e APK)

Enquanto for `http://IP:porta`, o app **funciona como site** (login, lançamentos,
PDF, e-mail), mas **PWA/instalação, o compartilhar-comprovante e o APK NÃO
funcionam** — esses recursos exigem HTTPS (contexto seguro).

Quando tiver um domínio (ex.: `bagual.seudominio.com`):

1. No DNS do domínio, crie um registro **A** apontando `bagual` para o IP da VM.
2. No compose, troque a porta para escutar só local:
   `- "127.0.0.1:${APP_PORT}:5000"` e recrie (`up -d`).
3. Crie um server block no Nginx:
   ```nginx
   server {
       server_name bagual.seudominio.com;
       location / {
           proxy_pass http://127.0.0.1:8083;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
4. Emita o certificado:
   ```bash
   sudo certbot --nginx -d bagual.seudominio.com
   ```

Pronto: `https://bagual.seudominio.com` funciona, o PWA instala, o compartilhar
comprovante aparece no Android, e dá pra gerar o APK (PWABuilder/Bubblewrap).

---

## HTTPS provisório SEM domínio (sslip.io)

Quer o HTTPS **agora**, antes de comprar domínio, pra já testar PWA/compartilhar/APK?
Use `sslip.io`: qualquer `SEU-IP.sslip.io` resolve automaticamente para `SEU-IP`, e o
Let's Encrypt emite certificado normalmente pra esse hostname.

1. **Descubra o IP público da VM:**
   ```bash
   curl -s ifconfig.me; echo
   ```
   Monte o hostname trocando os pontos por hífens. Ex.: IP `203.0.113.45` →
   `203-0-113-45.sslip.io`.

2. **Deixe a app escutando só localmente** (o Nginx vai expor com TLS).
   No `docker-compose.vm.yml`, troque a linha da porta por:
   ```yaml
       ports:
         - "127.0.0.1:${APP_PORT:-8083}:5000"
   ```
   e recrie: `docker compose -f docker-compose.vm.yml --env-file .env up -d`.

3. **Crie o server block do Nginx** (troque o hostname pelo seu):
   ```bash
   sudo tee /etc/nginx/sites-available/bagual >/dev/null <<'NGINX'
   server {
       listen 80;
       server_name 203-0-113-45.sslip.io;
       location / {
           proxy_pass http://127.0.0.1:8083;
           proxy_set_header Host              $host;
           proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   NGINX
   sudo ln -s /etc/nginx/sites-available/bagual /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```

4. **Emita o certificado** (o Certbot configura o 443 sozinho):
   ```bash
   sudo certbot --nginx -d 203-0-113-45.sslip.io
   ```

Pronto: `https://203-0-113-45.sslip.io` no ar com HTTPS — o PWA instala, o compartilhar
comprovante aparece no Android e dá pra gerar o APK. Quando comprar o domínio de verdade,
é só repetir os passos 3–4 com o nome novo.

> Observação: se as portas 80/443 já são usadas pelos outros sites, tudo bem — o Nginx
> roteia por `server_name`, então este server block convive com os existentes.
