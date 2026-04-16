import pytest
from app import app, get_conn


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test'
    with app.test_client() as c:
        yield c


@pytest.fixture
def logged_client(client):
    """Client já autenticado via sessão."""
    with client.session_transaction() as sess:
        sess['usuario_id']   = 1
        sess['usuario_nome'] = 'Teste'
    return client


@pytest.fixture(autouse=True)
def limpar_lancamentos_teste():
    """Remove lançamentos criados pelos testes após cada teste."""
    yield
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM lancamento WHERE descricao LIKE '[TEST]%'")
    conn.commit()
    cur.close(); conn.close()


# ── 1. login com credenciais corretas ─────────────────────────────────────────

def test_login_valido(client):
    resp = client.post('/', data={'login': 'fin_admin', 'senha': 'Fin407'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert 'Lançamentos'.encode() in resp.data


# ── 2. login com credenciais erradas ──────────────────────────────────────────

def test_login_invalido(client):
    resp = client.post('/', data={'login': 'admin', 'senha': 'errada'},
                       follow_redirects=True)
    assert 'inválidos'.encode() in resp.data


# ── 3. acesso sem login redireciona para login ─────────────────────────────────

def test_acesso_sem_login(client):
    resp = client.get('/lancamentos')
    assert resp.status_code == 302
    assert '/' in resp.headers['Location']


# ── 4. listagem acessível com login ───────────────────────────────────────────

def test_listagem_com_login(logged_client):
    resp = logged_client.get('/lancamentos')
    assert resp.status_code == 200
    assert 'Extrato'.encode() in resp.data


# ── 5. página de novo lançamento carrega ──────────────────────────────────────

def test_form_novo_carrega(logged_client):
    resp = logged_client.get('/lancamentos/novo')
    assert resp.status_code == 200
    assert 'Criar Lançamento'.encode() in resp.data


# ── 6. criar lançamento receita ───────────────────────────────────────────────

def test_criar_receita(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Receita unitária',
        'data_lancamento': '2026-01-10',
        'valor':           '1500.00',
        'tipo_lancamento': 'receita',
        'situacao':        'ativo',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'criado com sucesso'.encode() in resp.data


# ── 7. criar lançamento despesa ───────────────────────────────────────────────

def test_criar_despesa(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Despesa unitária',
        'data_lancamento': '2026-01-15',
        'valor':           '200.50',
        'tipo_lancamento': 'despesa',
        'situacao':        'ativo',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'criado com sucesso'.encode() in resp.data


# ── 8. criar lançamento sem descrição retorna erro ────────────────────────────

def test_criar_sem_descricao(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '',
        'data_lancamento': '2026-01-10',
        'valor':           '100.00',
        'tipo_lancamento': 'receita',
    })
    assert 'obrigatórios'.encode() in resp.data


# ── 9. criar lançamento sem valor retorna erro ────────────────────────────────

def test_criar_sem_valor(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Sem valor',
        'data_lancamento': '2026-01-10',
        'valor':           '',
        'tipo_lancamento': 'receita',
    })
    assert 'obrigatórios'.encode() in resp.data


# ── 10. criar lançamento inativo ──────────────────────────────────────────────

def test_criar_inativo(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Lançamento inativo',
        'data_lancamento': '2026-02-01',
        'valor':           '50.00',
        'tipo_lancamento': 'despesa',
        'situacao':        'inativo',
    }, follow_redirects=True)
    assert resp.status_code == 200

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT situacao FROM lancamento WHERE descricao = '[TEST] Lançamento inativo'")
    row = cur.fetchone()
    cur.close(); conn.close()
    assert row is not None and row[0] == 'inativo'


# ── 11. editar lançamento existente ───────────────────────────────────────────

def test_editar_lancamento(logged_client):
    # cria
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)"
        " VALUES ('[TEST] Original', '2026-03-01', 100, 'receita', 'ativo') RETURNING id"
    )
    lid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()

    # edita
    resp = logged_client.post(f'/lancamentos/editar/{lid}', data={
        'descricao':       '[TEST] Editado',
        'data_lancamento': '2026-03-05',
        'valor':           '250.00',
        'tipo_lancamento': 'receita',
        'situacao':        'ativo',
    }, follow_redirects=True)
    assert 'atualizado'.encode() in resp.data

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT descricao FROM lancamento WHERE id = %s", (lid,))
    assert cur.fetchone()[0] == '[TEST] Editado'
    cur.close(); conn.close()


# ── 12. editar lançamento inexistente redireciona ─────────────────────────────

def test_editar_inexistente(logged_client):
    resp = logged_client.get('/lancamentos/editar/999999')
    assert resp.status_code == 302


# ── 13. excluir lançamento ────────────────────────────────────────────────────

def test_excluir_lancamento(logged_client):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)"
        " VALUES ('[TEST] Para excluir', '2026-03-10', 10, 'despesa', 'ativo') RETURNING id"
    )
    lid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()

    resp = logged_client.post(f'/lancamentos/excluir/{lid}', follow_redirects=True)
    assert resp.status_code == 200

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM lancamento WHERE id = %s", (lid,))
    assert cur.fetchone() is None
    cur.close(); conn.close()


# ── 14. filtro por tipo receita ───────────────────────────────────────────────

def test_filtro_tipo_receita(logged_client):
    resp = logged_client.get('/lancamentos?tipo=receita')
    assert resp.status_code == 200
    # com filtro ativo, o chip de filtro aparece na página
    assert b'Tipo: receita' in resp.data


# ── 15. filtro por tipo despesa ───────────────────────────────────────────────

def test_filtro_tipo_despesa(logged_client):
    resp = logged_client.get('/lancamentos?tipo=despesa')
    assert resp.status_code == 200
    assert b'Tipo: despesa' in resp.data


# ── 16. filtro por situação inativo ───────────────────────────────────────────

def test_filtro_situacao_inativo(logged_client):
    resp = logged_client.get('/lancamentos?situacao=inativo')
    assert resp.status_code == 200
    assert b'badge-inativo' in resp.data


# ── 17. filtro por intervalo de datas ─────────────────────────────────────────

def test_filtro_data(logged_client):
    resp = logged_client.get('/lancamentos?data_ini=2026-01-01&data_fim=2026-12-31')
    assert resp.status_code == 200


# ── 18. exportar PDF retorna arquivo PDF ──────────────────────────────────────

def test_exportar_pdf(logged_client):
    resp = logged_client.get('/lancamentos/exportar-pdf')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.data[:4] == b'%PDF'


# ── 19. exportar PDF com filtro ───────────────────────────────────────────────

def test_exportar_pdf_com_filtro(logged_client):
    resp = logged_client.get('/lancamentos/exportar-pdf?tipo=receita')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'


# ── 20. logout encerra sessão ─────────────────────────────────────────────────

def test_logout(logged_client):
    resp = logged_client.get('/logout', follow_redirects=True)
    assert resp.status_code == 200
    # após logout, /lancamentos deve redirecionar
    resp2 = logged_client.get('/lancamentos')
    assert resp2.status_code == 302
