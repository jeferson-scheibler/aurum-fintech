import pytest
from app import app, get_conn


# fixtures

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test'
    with app.test_client() as c:
        yield c


@pytest.fixture
def logged_client(client):
    with client.session_transaction() as sess:
        sess['usuario_id']    = 1
        sess['usuario_nome']  = 'Teste'
        sess['usuario_email'] = ''
    return client


@pytest.fixture(autouse=True)
def limpar_lancamentos_teste():
    yield
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM lancamento WHERE descricao LIKE '[TEST]%'")
    conn.commit()
    cur.close()
    conn.close()


# login e sessão

def test_login_valido(client):
    resp = client.post('/', data={'login': 'admin', 'senha': 'admin123'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert 'Lançamentos'.encode() in resp.data


def test_login_invalido(client):
    resp = client.post('/', data={'login': 'admin', 'senha': 'errada'},
                       follow_redirects=True)
    assert 'inválidos'.encode() in resp.data


def test_acesso_sem_login_redireciona(client):
    resp = client.get('/lancamentos')
    assert resp.status_code == 302


def test_logout_encerra_sessao(logged_client):
    logged_client.get('/logout')
    resp = logged_client.get('/lancamentos')
    assert resp.status_code == 302


# listagem e perfil

def test_listagem_acessivel(logged_client):
    resp = logged_client.get('/lancamentos')
    assert resp.status_code == 200
    assert 'Extrato'.encode() in resp.data


def test_perfil_carrega(logged_client):
    resp = logged_client.get('/perfil')
    assert resp.status_code == 200


def test_form_novo_carrega(logged_client):
    resp = logged_client.get('/lancamentos/novo')
    assert resp.status_code == 200
    assert 'Criar Lançamento'.encode() in resp.data


# criar lançamentos

def test_criar_receita(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Salário mensal',
        'data_lancamento': '2026-01-10',
        'valor':           '5000.00',
        'tipo_lancamento': 'receita',
        'situacao':        'ativo',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'criado com sucesso'.encode() in resp.data


def test_criar_despesa(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Conta de luz',
        'data_lancamento': '2026-01-15',
        'valor':           '180.50',
        'tipo_lancamento': 'despesa',
        'situacao':        'ativo',
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'criado com sucesso'.encode() in resp.data


def test_criar_com_observacao(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Freelance com obs',
        'data_lancamento': '2026-02-01',
        'valor':           '800.00',
        'tipo_lancamento': 'receita',
        'situacao':        'ativo',
        'observacao':      'Projeto site cliente X',
    }, follow_redirects=True)
    assert 'criado com sucesso'.encode() in resp.data

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT observacao FROM lancamento WHERE descricao = '[TEST] Freelance com obs'")
    row = cur.fetchone()
    cur.close(); conn.close()
    assert row is not None and row[0] == 'Projeto site cliente X'


def test_criar_inativo(logged_client):
    logged_client.post('/lancamentos/novo', data={
        'descricao':       '[TEST] Lançamento suspenso',
        'data_lancamento': '2026-02-10',
        'valor':           '50.00',
        'tipo_lancamento': 'despesa',
        'situacao':        'inativo',
    }, follow_redirects=True)

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT situacao FROM lancamento WHERE descricao = '[TEST] Lançamento suspenso'")
    row = cur.fetchone()
    cur.close(); conn.close()
    assert row is not None and row[0] == 'inativo'


# validações de campos obrigatórios

def test_criar_sem_descricao(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao': '', 'data_lancamento': '2026-01-10',
        'valor': '100.00', 'tipo_lancamento': 'receita',
    })
    assert 'obrigatórios'.encode() in resp.data


def test_criar_sem_valor(logged_client):
    resp = logged_client.post('/lancamentos/novo', data={
        'descricao': '[TEST] Sem valor', 'data_lancamento': '2026-01-10',
        'valor': '', 'tipo_lancamento': 'receita',
    })
    assert 'obrigatórios'.encode() in resp.data


# editar e excluir

def test_editar_lancamento(logged_client):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)"
        " VALUES ('[TEST] Original', '2026-03-01', 100, 'receita', 'ativo') RETURNING id"
    )
    lid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()

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


def test_editar_inexistente(logged_client):
    resp = logged_client.get('/lancamentos/editar/999999')
    assert resp.status_code == 302


def test_excluir_lancamento(logged_client):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)"
        " VALUES ('[TEST] Para excluir', '2026-03-10', 10, 'despesa', 'ativo') RETURNING id"
    )
    lid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()

    logged_client.post(f'/lancamentos/excluir/{lid}', follow_redirects=True)

    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT id FROM lancamento WHERE id = %s", (lid,))
    assert cur.fetchone() is None
    cur.close(); conn.close()


# filtros

def test_filtro_tipo_receita(logged_client):
    resp = logged_client.get('/lancamentos?tipo=receita')
    assert resp.status_code == 200
    assert b'Tipo: receita' in resp.data


def test_filtro_tipo_despesa(logged_client):
    resp = logged_client.get('/lancamentos?tipo=despesa')
    assert resp.status_code == 200
    assert b'Tipo: despesa' in resp.data


def test_filtro_situacao_inativo(logged_client):
    # garante que existe pelo menos um inativo antes de filtrar
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)"
        " VALUES ('[TEST] Inativo filtro', '2026-04-01', 30, 'despesa', 'inativo')"
    )
    conn.commit(); cur.close(); conn.close()

    resp = logged_client.get('/lancamentos?situacao=inativo')
    assert resp.status_code == 200
    assert b'[TEST] Inativo filtro' in resp.data


def test_filtro_data(logged_client):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)"
        " VALUES ('[TEST] Julho especifico', '2026-07-20', 999, 'receita', 'ativo')"
    )
    conn.commit(); cur.close(); conn.close()

    resp = logged_client.get('/lancamentos?data_ini=2026-07-01&data_fim=2026-07-31')
    assert resp.status_code == 200
    assert b'[TEST] Julho especifico' in resp.data


# exportação PDF

def test_exportar_pdf(logged_client):
    resp = logged_client.get('/lancamentos/exportar-pdf')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.data[:4] == b'%PDF'


def test_exportar_pdf_com_filtro(logged_client):
    resp = logged_client.get('/lancamentos/exportar-pdf?tipo=receita')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
