# Aurum Fintech

Aplicação web para controle de receitas e despesas, desenvolvida como projeto prático da disciplina **Gerência de Configuração de Software (4815207)** — Univates 2026/A.

---

## Arquitetura geral

```
┌─────────────────────────────────────────────────────────────────┐
│  Workspace local (dev)                                          │
│  Windows / Linux / macOS  ──  Git + GitHub Issues               │
└───────────────────────────┬─────────────────────────────────────┘
                            │ git push / pull request
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  GitHub (Versionamento + Controle de Mudança + CI)              │
│                                                                 │
│  GitHub Issues  ──►  Pull Request  ──►  GitHub Actions          │
│                                              │                  │
│                          ┌───────────────────┤                  │
│                          ▼                   ▼                  │
│                      job: test          job: quality            │
│                      pytest (20)        SonarCloud              │
│                      pytest-html             │                  │
│                          │                   │                  │
│                          └────────┬──────────┘                  │
│                                   ▼                             │
│                              job: build                         │
│                              docker build                       │
└───────────────────────────────────────────────────────────────--┘
                            │ deploy manual (script)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  VM Univates  ──  Ubuntu  ──  IP: 177.44.248.105                │
│                                                                 │
│  ┌─────────────────────────┐  ┌─────────────────────────┐      │
│  │  Homologação (:8081)    │  │  Produção (:8082)        │      │
│  │                         │  │                          │      │
│  │  [aurum_db_homolog]     │  │  [aurum_db_prod]         │      │
│  │  PostgreSQL 16-alpine   │  │  PostgreSQL 16-alpine    │      │
│  │          │              │  │          │               │      │
│  │  [aurum_flyway_homolog] │  │  [aurum_flyway_prod]     │      │
│  │  Flyway 10-alpine       │  │  Flyway 10-alpine        │      │
│  │          │              │  │          │               │      │
│  │  [aurum_app_homolog]    │  │  [aurum_app_prod]        │      │
│  │  Python 3.12-slim       │  │  Python 3.12-slim        │      │
│  └─────────────────────────┘  └─────────────────────────┘      │
│         Docker Compose                Docker Compose            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stack de tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Framework web | Flask 3.1 |
| Banco de dados | PostgreSQL 16 |
| Versionamento do banco | Flyway 10 |
| Contêineres | Docker + Docker Compose |
| Sistema Operacional (VM) | Ubuntu (VM Univates) |
| Controle de mudança | GitHub Issues |
| Versionamento de código | Git + GitHub |
| Integração contínua | GitHub Actions |
| Testes automatizados | pytest + pytest-html |
| Qualidade de código | SonarCloud |

---

## Pipeline CI/CD

O pipeline é disparado automaticamente a cada `push` ou `pull request` na branch `main`.

```
[push/PR] ──► test ──► quality ──► build
```

**job `test`**
- Sobe um container PostgreSQL 16 como service do runner
- Aplica as migrations com Flyway via Docker
- Executa os 20 testes com `pytest -v`
- Gera o relatório HTML (`relatorio-testes.html`) e publica como artifact

**job `quality`** *(depende de `test`)*
- Executa o scan do SonarCloud para análise estática do código

**job `build`** *(depende de `test` e `quality`)*
- Constrói a imagem Docker da aplicação para validar que o build está íntegro

---

## Fluxo de uma mudança

1. **Registrar** — abrir uma Issue no GitHub descrevendo a mudança
2. **Implementar** — código-fonte em `app.py`/`templates/` e, se necessário, nova migration em `migrations/`
3. **Versionar** — commit com referência à issue (`closes #N`) e push para o GitHub
4. **Integração automática** — GitHub Actions executa testes, qualidade e build
5. **Atualizar Homolog** — rodar `./deploy-homolog.sh` na VM
6. **Validar em Homolog** — acessar `http://177.44.248.105:8081` e verificar a mudança + migrations aplicadas
7. **Atualizar Produção** — rodar `./deploy-prod.sh` na VM
8. **Validar em Prod** — acessar `http://177.44.248.105:8082`

Os scripts de deploy são semi-automatizados: um único comando recria os containers e aplica as migrations automaticamente via Flyway.

---

## Versionamento do banco de dados

As migrations ficam em `migrations/` seguindo o padrão Flyway (`V{n}__{descricao}.sql`). O Flyway é executado como container separado antes da aplicação subir, tanto no CI quanto nos ambientes de homolog e produção.

```
migrations/
├── V1__init.sql          # cria tabelas usuario e lancamento
├── V2__seed_inicial.sql  # dados iniciais (usuário admin + lançamentos de exemplo)
└── V3__add_observacao.sql# adiciona coluna observacao em lancamento
```

---

## Testes automatizados

São 22 testes cobrindo os principais fluxos da aplicação:

| # | Teste |
|---|---|
| 1 | Login com credenciais corretas |
| 2 | Login com credenciais inválidas |
| 3 | Acesso sem autenticação redireciona para login |
| 4 | Logout encerra a sessão |
| 5 | Listagem de lançamentos acessível com login |
| 6 | Página de perfil carrega |
| 7 | Formulário de novo lançamento carrega |
| 8 | Criar lançamento do tipo receita |
| 9 | Criar lançamento do tipo despesa |
| 10 | Criar lançamento com observação e verificar persistência no banco |
| 11 | Criar lançamento com situação inativo |
| 12 | Criar lançamento sem descrição retorna erro de validação |
| 13 | Criar lançamento sem valor retorna erro de validação |
| 14 | Editar lançamento existente e verificar atualização no banco |
| 15 | Editar lançamento inexistente redireciona |
| 16 | Excluir lançamento e verificar remoção no banco |
| 17 | Filtro por tipo receita |
| 18 | Filtro por tipo despesa |
| 19 | Filtro por situação inativo (com registro garantido no banco) |
| 20 | Filtro por intervalo de datas (com registro de data conhecida) |
| 21 | Exportar PDF da listagem completa |
| 22 | Exportar PDF com filtro aplicado |

O relatório de execução é gerado em HTML pelo `pytest-html` e publicado como artifact no GitHub Actions após cada pipeline.

Para rodar localmente (requer banco configurado):

```bash
pip install flask psycopg2-binary python-dotenv reportlab pytest pytest-html
pytest test_app.py -v --html=relatorio-testes.html --self-contained-html
```

---

## Qualidade de código

O projeto está integrado ao [SonarCloud](https://sonarcloud.io/project/overview?id=aurum-fintech). A análise roda automaticamente no pipeline após os testes passarem, usando as configurações em `sonar-project.properties`.

---

## Ambientes

### Criar do zero

```bash
# Homologação
docker compose -f docker-compose.homolog.yml up -d --build

# Produção
docker compose -f docker-compose.prod.yml up -d --build
```

### Atualizar (semi-automatizado)

```bash
./deploy-homolog.sh   # atualiza homolog em http://177.44.248.105:8081
./deploy-prod.sh      # atualiza produção em http://177.44.248.105:8082
```

Cada script reconstrói a imagem da aplicação e reaplica as migrations via Flyway, sem intervenção manual além de executar o script.

---

## Estrutura do projeto

```
aurum-fintech/
├── .github/workflows/ci.yml       # pipeline GitHub Actions
├── migrations/                    # migrations Flyway
├── templates/                     # páginas HTML (Jinja2)
├── app.py                         # rotas e lógica da aplicação
├── test_app.py                    # 20 testes automatizados
├── Dockerfile                     # imagem da aplicação
├── docker-compose.homolog.yml     # ambiente de homologação
├── docker-compose.prod.yml        # ambiente de produção
├── deploy-homolog.sh              # script de deploy homolog
├── deploy-prod.sh                 # script de deploy produção
├── sonar-project.properties       # configuração SonarCloud
└── requirements.txt               # dependências Python
```
