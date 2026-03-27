from flask import Flask, render_template, redirect, url_for, session, request, flash
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = 'aurum_secret_2026'

DB_CONFIG = {
    'dbname': 'financas_db',
    'user': 'fintech',
    'password': 'Fin407',
    'host': 'localhost',
    'port': 5432
}

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ── LOGIN ──────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        login_input = request.form['login']
        senha_input = request.form['senha']
        try:
            conn = get_conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM usuario WHERE login = %s AND senha = %s AND situacao = 'ativo'",
                (login_input, senha_input)
            )
            usuario = cur.fetchone()
            cur.close()
            conn.close()
            if usuario:
                session['usuario_id'] = usuario['id']
                session['usuario_nome'] = usuario['nome']
                return redirect(url_for('lancamentos'))
            else:
                erro = 'Login ou senha inválidos.'
        except Exception as e:
            erro = f'Erro ao conectar ao banco: {e}'
    return render_template('login.html', erro=erro)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── LISTAR ─────────────────────────────────────────────────────────────────────

@app.route('/lancamentos')
@login_required
def lancamentos():
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM lancamento ORDER BY data_lancamento DESC")
        registros = cur.fetchall()
        cur.close()
        conn.close()

        ativos = [r for r in registros if r['situacao'] == 'ativo']
        total_receitas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'receita')
        total_despesas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'despesa')
        saldo = total_receitas - total_despesas
    except Exception as e:
        registros = []
        total_receitas = total_despesas = saldo = 0

    return render_template(
        'lancamentos.html',
        registros=registros,
        total_receitas=total_receitas,
        total_despesas=total_despesas,
        saldo=saldo,
        usuario_nome=session.get('usuario_nome')
    )


# ── CRIAR ──────────────────────────────────────────────────────────────────────

@app.route('/lancamentos/novo', methods=['GET', 'POST'])
@login_required
def novo_lancamento():
    erro = None
    if request.method == 'POST':
        descricao       = request.form['descricao'].strip()
        data_lancamento = request.form['data_lancamento']
        valor           = request.form['valor'].replace(',', '.')
        tipo_lancamento = request.form['tipo_lancamento']
        situacao        = request.form.get('situacao', 'ativo')

        if not descricao or not data_lancamento or not valor or not tipo_lancamento:
            erro = 'Preencha todos os campos obrigatórios.'
        else:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (descricao, data_lancamento, float(valor), tipo_lancamento, situacao)
                )
                conn.commit()
                cur.close()
                conn.close()
                flash('Lançamento criado com sucesso.', 'ok')
                return redirect(url_for('lancamentos'))
            except Exception as e:
                erro = f'Erro ao salvar: {e}'

    return render_template('form_lancamento.html',
                           acao='Novo', lancamento=None, erro=erro,
                           usuario_nome=session.get('usuario_nome'))


# ── EDITAR ─────────────────────────────────────────────────────────────────────

@app.route('/lancamentos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_lancamento(id):
    erro = None
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if request.method == 'POST':
        descricao       = request.form['descricao'].strip()
        data_lancamento = request.form['data_lancamento']
        valor           = request.form['valor'].replace(',', '.')
        tipo_lancamento = request.form['tipo_lancamento']
        situacao        = request.form.get('situacao', 'ativo')

        if not descricao or not data_lancamento or not valor or not tipo_lancamento:
            erro = 'Preencha todos os campos obrigatórios.'
        else:
            try:
                cur.execute(
                    """UPDATE lancamento
                       SET descricao=%s, data_lancamento=%s, valor=%s,
                           tipo_lancamento=%s, situacao=%s
                       WHERE id=%s""",
                    (descricao, data_lancamento, float(valor), tipo_lancamento, situacao, id)
                )
                conn.commit()
                cur.close()
                conn.close()
                flash('Lançamento atualizado com sucesso.', 'ok')
                return redirect(url_for('lancamentos'))
            except Exception as e:
                erro = f'Erro ao atualizar: {e}'

    cur.execute("SELECT * FROM lancamento WHERE id = %s", (id,))
    lancamento = cur.fetchone()
    cur.close()
    conn.close()

    if not lancamento:
        return redirect(url_for('lancamentos'))

    return render_template('form_lancamento.html',
                           acao='Editar', lancamento=lancamento, erro=erro,
                           usuario_nome=session.get('usuario_nome'))


# ── EXCLUIR ────────────────────────────────────────────────────────────────────

@app.route('/lancamentos/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_lancamento(id):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM lancamento WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        flash('Lançamento excluído.', 'ok')
    except Exception as e:
        flash(f'Erro ao excluir: {e}', 'erro')
    return redirect(url_for('lancamentos'))


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
