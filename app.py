from flask import Flask, render_template, redirect, url_for, session, request, flash, make_response
import psycopg2
import psycopg2.extras
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph, Frame

from dotenv import load_dotenv
import os
load_dotenv()

app = Flask(__name__)
app.secret_key = 'aurum_secret_2026'

DB_CONFIG = {
    'dbname': 'financas_db',
    'user': 'fintech',
    'password': 'Fin407',
    'host': 'localhost',
    'port': 5432
}

SMTP_HOST    = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT    = int(os.getenv('SMTP_PORT', 587))
SMTP_USUARIO = os.getenv('SMTP_USUARIO', '')
SMTP_SENHA   = os.getenv('SMTP_SENHA', '')


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


def _email_html(acao, campos):
    cor_acao   = '#4caf7d' if acao == 'criado' else '#C9A84C'
    label_acao = 'Novo Lançamento' if acao == 'criado' else 'Lançamento Atualizado'
    tipo       = campos.get('tipo_lancamento', '')
    cor_tipo   = '#4caf7d' if tipo == 'receita' else '#c97a7a'
    valor_fmt  = f"R$ {float(campos.get('valor', 0)):,.2f}".replace(',','X').replace('.',',').replace('X','.')

    def row(label, valor, cor='#E8E2D0'):
        return (
            '<tr>'
            f'<td style="padding:10px 0;border-bottom:1px solid #2a2820;font-size:10px;'
            f'letter-spacing:.15em;text-transform:uppercase;color:#6b6550;width:36%;">{label}</td>'
            f'<td style="padding:10px 0;border-bottom:1px solid #2a2820;font-size:13px;'
            f'color:{cor};font-family:\'Courier New\',monospace;">{valor}</td>'
            '</tr>'
        )

    rows = (
          row('ID',        f"#{campos.get('id', '—')}")
        + row('Descrição', campos.get('descricao', ''))
        + row('Data',      campos.get('data_lancamento', ''))
        + row('Tipo',      tipo.capitalize(), cor_tipo)
        + row('Valor',     valor_fmt, cor_tipo)
        + row('Situação',  campos.get('situacao', '').capitalize())
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#0B0B0E;font-family:'Courier New',Courier,monospace;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0B0B0E;padding:40px 0;">
<tr><td align="center">
<table width="540" cellpadding="0" cellspacing="0"
       style="background:#111116;border:1px solid #2a2820;max-width:540px;width:100%;">

  <tr><td style="height:2px;background:linear-gradient(90deg,transparent,#C9A84C,transparent);font-size:0;">&nbsp;</td></tr>

  <tr>
    <td style="padding:32px 36px 24px;border-bottom:1px solid #2a2820;">
      <span style="font-size:26px;color:#C9A84C;font-family:Georgia,serif;font-weight:300;">&#9419;</span>
      <span style="font-size:14px;color:#E8E2D0;font-family:Georgia,serif;
                   letter-spacing:.28em;text-transform:uppercase;margin-left:8px;">AURUM</span>
      <p style="margin:10px 0 0;font-size:9px;letter-spacing:.22em;
                text-transform:uppercase;color:#6b6550;">Gestão Financeira</p>
    </td>
  </tr>

  <tr>
    <td style="padding:24px 36px 0;">
      <span style="display:inline-block;font-size:9px;letter-spacing:.2em;
                   text-transform:uppercase;padding:5px 14px;
                   border:1px solid {cor_acao};color:{cor_acao};">{label_acao}</span>
    </td>
  </tr>

  <tr>
    <td style="padding:18px 36px 28px;">
      <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
    </td>
  </tr>

  <tr>
    <td style="padding:18px 36px 24px;border-top:1px solid #2a2820;">
      <p style="margin:0;font-size:9px;letter-spacing:.15em;
                text-transform:uppercase;color:#6b6550;">
        {datetime.now().strftime('%d/%m/%Y às %H:%M')} &nbsp;·&nbsp; Aurum Fintech
      </p>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def enviar_email(assunto, campos, acao, email_destinatario):
    if not SMTP_USUARIO or not SMTP_SENHA or not email_destinatario:
        app.logger.warning('E-mail não configurado.')
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From']    = SMTP_USUARIO
        msg['To']      = email_destinatario
        msg.attach(MIMEText(_email_html(acao, campos), 'html', 'utf-8'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USUARIO, SMTP_SENHA)
            smtp.sendmail(SMTP_USUARIO, email_destinatario, msg.as_string())
    except Exception as e:
        app.logger.warning(f'Falha ao enviar e-mail: {e}')


# ── LOGIN ──────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        login_input = request.form['login']
        senha_input = request.form['senha']
        try:
            conn = get_conn()
            cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT * FROM usuario WHERE login = %s AND senha = %s AND situacao = 'ativo'",
                (login_input, senha_input)
            )
            usuario = cur.fetchone()
            cur.close(); conn.close()
            if usuario:
                session['usuario_id']    = usuario['id']
                session['usuario_nome']  = usuario['nome']
                session['usuario_email'] = usuario['email'] or ''
                return redirect(url_for('lancamentos'))
            erro = 'Login ou senha inválidos.'
        except Exception as e:
            erro = f'Erro ao conectar ao banco: {e}'
    return render_template('login.html', erro=erro)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── PERFIL ─────────────────────────────────────────────────────────────────────

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    erro = None
    ok   = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        try:
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute(
                "UPDATE usuario SET email = %s WHERE id = %s",
                (email, session['usuario_id'])
            )
            conn.commit()
            cur.close(); conn.close()
            session['usuario_email'] = email
            ok = 'E-mail atualizado com sucesso.'
        except Exception as e:
            erro = f'Erro ao salvar: {e}'

    return render_template('perfil.html',
                           usuario_nome=session.get('usuario_nome'),
                           usuario_email=session.get('usuario_email', ''),
                           erro=erro, ok=ok)


# ── LISTAR ─────────────────────────────────────────────────────────────────────

@app.route('/lancamentos')
@login_required
def lancamentos():
    filtro_tipo     = request.args.get('tipo', '')
    filtro_situacao = request.args.get('situacao', '')
    filtro_data_ini = request.args.get('data_ini', '')
    filtro_data_fim = request.args.get('data_fim', '')

    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query, params = "SELECT * FROM lancamento WHERE 1=1", []
        if filtro_tipo:
            query += " AND tipo_lancamento = %s"; params.append(filtro_tipo)
        if filtro_situacao:
            query += " AND situacao = %s";        params.append(filtro_situacao)
        if filtro_data_ini:
            query += " AND data_lancamento >= %s"; params.append(filtro_data_ini)
        if filtro_data_fim:
            query += " AND data_lancamento <= %s"; params.append(filtro_data_fim)
        query += " ORDER BY data_lancamento DESC"

        cur.execute(query, params)
        registros = cur.fetchall()
        cur.close(); conn.close()

        ativos         = [r for r in registros if r['situacao'] == 'ativo']
        total_receitas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'receita')
        total_despesas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'despesa')
        saldo          = total_receitas - total_despesas
    except Exception:
        registros = []
        total_receitas = total_despesas = saldo = 0

    return render_template(
        'lancamentos.html',
        registros=registros,
        total_receitas=total_receitas,
        total_despesas=total_despesas,
        saldo=saldo,
        usuario_nome=session.get('usuario_nome'),
        filtro_tipo=filtro_tipo,
        filtro_situacao=filtro_situacao,
        filtro_data_ini=filtro_data_ini,
        filtro_data_fim=filtro_data_fim,
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

        if not all([descricao, data_lancamento, valor, tipo_lancamento]):
            erro = 'Preencha todos os campos obrigatórios.'
        else:
            try:
                conn = get_conn()
                cur  = conn.cursor()
                cur.execute(
                    """INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                    (descricao, data_lancamento, float(valor), tipo_lancamento, situacao)
                )
                novo_id = cur.fetchone()[0]
                conn.commit()
                cur.close(); conn.close()

                flash('Lançamento criado com sucesso.', 'ok')
                enviar_email(
                    assunto=f'[Aurum] Novo lançamento — {descricao}',
                    campos=dict(id=novo_id, descricao=descricao, data_lancamento=data_lancamento,
                                valor=valor, tipo_lancamento=tipo_lancamento, situacao=situacao),
                    acao='criado',
                    email_destinatario=session.get('usuario_email', ''),
                )
                return redirect(url_for('lancamentos'))
            except Exception as e:
                erro = f'Erro ao salvar: {e}'

    return render_template('form_lancamento.html', acao='Novo', lancamento=None,
                           erro=erro, usuario_nome=session.get('usuario_nome'))


# ── EDITAR ─────────────────────────────────────────────────────────────────────

@app.route('/lancamentos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_lancamento(id):
    erro = None
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if request.method == 'POST':
        descricao       = request.form['descricao'].strip()
        data_lancamento = request.form['data_lancamento']
        valor           = request.form['valor'].replace(',', '.')
        tipo_lancamento = request.form['tipo_lancamento']
        situacao        = request.form.get('situacao', 'ativo')

        if not all([descricao, data_lancamento, valor, tipo_lancamento]):
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
                cur.close(); conn.close()

                flash('Lançamento atualizado.', 'ok')
                enviar_email(
                    assunto=f'[Aurum] Lançamento atualizado — {descricao}',
                    campos=dict(id=id, descricao=descricao, data_lancamento=data_lancamento,
                                valor=valor, tipo_lancamento=tipo_lancamento, situacao=situacao),
                    acao='atualizado',
                    email_destinatario=session.get('usuario_email', ''),
                )
                return redirect(url_for('lancamentos'))
            except Exception as e:
                erro = f'Erro ao atualizar: {e}'

    cur.execute("SELECT * FROM lancamento WHERE id = %s", (id,))
    lancamento = cur.fetchone()
    cur.close(); conn.close()

    if not lancamento:
        return redirect(url_for('lancamentos'))

    return render_template('form_lancamento.html', acao='Editar', lancamento=lancamento,
                           erro=erro, usuario_nome=session.get('usuario_nome'))


# ── EXCLUIR ────────────────────────────────────────────────────────────────────

@app.route('/lancamentos/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_lancamento(id):
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("DELETE FROM lancamento WHERE id = %s", (id,))
        conn.commit()
        cur.close(); conn.close()
        flash('Lançamento excluído.', 'ok')
    except Exception as e:
        flash(f'Erro ao excluir: {e}', 'erro')
    return redirect(url_for('lancamentos'))


# ── EXPORTAR PDF ───────────────────────────────────────────────────────────────

@app.route('/lancamentos/exportar-pdf')
@login_required
def exportar_pdf():
    filtro_tipo     = request.args.get('tipo', '')
    filtro_situacao = request.args.get('situacao', '')
    filtro_data_ini = request.args.get('data_ini', '')
    filtro_data_fim = request.args.get('data_fim', '')

    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query, params = "SELECT * FROM lancamento WHERE 1=1", []
    if filtro_tipo:
        query += " AND tipo_lancamento = %s"; params.append(filtro_tipo)
    if filtro_situacao:
        query += " AND situacao = %s";        params.append(filtro_situacao)
    if filtro_data_ini:
        query += " AND data_lancamento >= %s"; params.append(filtro_data_ini)
    if filtro_data_fim:
        query += " AND data_lancamento <= %s"; params.append(filtro_data_fim)
    query += " ORDER BY data_lancamento DESC"
    cur.execute(query, params)
    registros = cur.fetchall()
    cur.close(); conn.close()

    ativos         = [r for r in registros if r['situacao'] == 'ativo']
    total_receitas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'receita')
    total_despesas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'despesa')
    saldo          = total_receitas - total_despesas

    GOLD    = colors.HexColor('#C9A84C')
    DARK    = colors.HexColor('#0B0B0E')
    SURFACE = colors.HexColor('#111116')
    SURFACE2= colors.HexColor('#16161c')
    GREEN   = colors.HexColor('#4caf7d')
    RED     = colors.HexColor('#c97a7a')
    MUTED   = colors.HexColor('#6b6550')
    TEXT    = colors.HexColor('#E8E2D0')
    BORDER  = colors.HexColor('#2a2820')

    PAGE_W, PAGE_H = A4
    M = 15 * mm

    def fmt(v):
        return f'R$ {v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    def draw_page(c):
        c.saveState()

        c.setFillColor(DARK)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        stripe_h = 2.5
        thirds   = (PAGE_W - 2 * M) / 3
        for i, alpha in enumerate([0.2, 1.0, 0.2]):
            c.setFillColorRGB(GOLD.red, GOLD.green, GOLD.blue, alpha)
            c.rect(M + i * thirds, PAGE_H - stripe_h, thirds, stripe_h, fill=1, stroke=0)

        c.setFont('Helvetica-Bold', 22)
        c.setFillColor(GOLD)
        c.drawString(M, PAGE_H - 18 * mm, 'AURUM')

        c.setFont('Helvetica', 8)
        c.setFillColor(MUTED)
        c.drawString(M, PAGE_H - 23 * mm, 'GESTAO FINANCEIRA')
        c.drawRightString(PAGE_W - M, PAGE_H - 18 * mm,
                          f'Extrato de Lancamentos  .  {datetime.now().strftime("%d/%m/%Y")}')

        sep_y = PAGE_H - 27 * mm
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.5)
        c.line(M, sep_y, PAGE_W - M, sep_y)

        card_y    = sep_y - 22 * mm
        card_h    = 18 * mm
        card_w    = (PAGE_W - 2 * M) / 3
        card_data = [
            ('TOTAL RECEITAS', fmt(total_receitas), GREEN),
            ('TOTAL DESPESAS', fmt(total_despesas), RED),
            ('SALDO',          fmt(saldo),          GOLD),
        ]
        for i, (label, valor, cor) in enumerate(card_data):
            cx = M + i * card_w
            c.setFillColor(SURFACE)
            c.rect(cx, card_y, card_w, card_h, fill=1, stroke=0)
            if i > 0:
                c.setStrokeColor(BORDER)
                c.setLineWidth(0.4)
                c.line(cx, card_y, cx, card_y + card_h)
            c.setFillColor(cor)
            c.rect(cx, card_y + card_h - 2, card_w, 2, fill=1, stroke=0)
            c.setFont('Helvetica', 7)
            c.setFillColor(MUTED)
            c.drawString(cx + 8, card_y + card_h - 10, label)
            c.setFont('Helvetica-Bold', 13)
            c.setFillColor(cor)
            c.drawString(cx + 8, card_y + 5, valor)

        c.setStrokeColor(BORDER)
        c.setLineWidth(0.4)
        c.rect(M, card_y, PAGE_W - 2 * M, card_h, fill=0, stroke=1)

        footer_y = 10 * mm
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.4)
        c.line(M, footer_y + 4 * mm, PAGE_W - M, footer_y + 4 * mm)
        c.setFont('Helvetica', 7)
        c.setFillColor(MUTED)
        c.drawString(M, footer_y, 'AURUM FINTECH')
        c.drawRightString(PAGE_W - M, footer_y,
                          f'Gerado em {datetime.now().strftime("%d/%m/%Y as %H:%M")}')

        c.restoreState()
        return card_y - 6 * mm

    base   = getSampleStyleSheet()
    normal = base['Normal']

    def ps(name, **kw):
        return ParagraphStyle(name, parent=normal, **kw)

    head_s = ps('h',  fontSize=7, textColor=GOLD,  fontName='Helvetica-Bold')
    cell_s = ps('c',  fontSize=8, textColor=TEXT,  fontName='Helvetica')
    cell_m = ps('cm', fontSize=8, textColor=MUTED, fontName='Helvetica')

    def mkcell(text, style, cor=None):
        if cor:
            return Paragraph(f'<font color="{cor}">{text}</font>', style)
        return Paragraph(text, style)

    col_w = [10*mm, 67*mm, 24*mm, 20*mm, 34*mm, 18*mm]

    rows = [[
        mkcell('#',         head_s),
        mkcell('DESCRICAO', head_s),
        mkcell('DATA',      head_s),
        mkcell('TIPO',      head_s),
        mkcell('VALOR',     head_s),
        mkcell('SITUACAO',  head_s),
    ]]
    for r in registros:
        receita = r['tipo_lancamento'] == 'receita'
        cor_val = '#4caf7d' if receita else '#c97a7a'
        sinal   = '' if receita else '- '
        rows.append([
            mkcell(str(r['id']),                              cell_m),
            mkcell(r['descricao'],                            cell_s),
            mkcell(r['data_lancamento'].strftime('%d/%m/%Y'), cell_m),
            mkcell('Receita' if receita else 'Despesa',       cell_s, cor_val),
            mkcell(f"{sinal}{fmt(r['valor'])}",               cell_s, cor_val),
            mkcell('Ativo' if r['situacao'] == 'ativo' else 'Inativo', cell_m,
                   None if r['situacao'] == 'ativo' else '#6b6550'),
        ])

    tabela = Table(rows, colWidths=col_w, repeatRows=1)
    tabela.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#0d0d10')),
        ('LINEBELOW',     (0,0), (-1,0), 0.8, GOLD),
        ('TOPPADDING',    (0,0), (-1,0), 7),
        ('BOTTOMPADDING', (0,0), (-1,0), 7),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [SURFACE, SURFACE2]),
        ('LINEBELOW',     (0,1), (-1,-1), 0.3, BORDER),
        ('TOPPADDING',    (0,1), (-1,-1), 5),
        ('BOTTOMPADDING', (0,1), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ('RIGHTPADDING',  (0,0), (-1,-1), 6),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('BOX',           (0,0), (-1,-1), 0.4, BORDER),
    ]))

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    def render_all():
        table_top = draw_page(c)
        frame_h   = table_top - 14 * mm
        frame     = Frame(M, 14 * mm, PAGE_W - 2 * M, frame_h,
                          leftPadding=0, rightPadding=0,
                          topPadding=0,  bottomPadding=0)
        story     = [tabela]
        remaining = frame.addFromList(story, c)

        while remaining:
            c.showPage()
            draw_page(c)
            frame2 = Frame(M, 14 * mm, PAGE_W - 2 * M, frame_h,
                           leftPadding=0, rightPadding=0,
                           topPadding=0,  bottomPadding=0)
            remaining = frame2.addFromList(remaining, c)

        c.save()

    render_all()
    buffer.seek(0)

    resp = make_response(buffer.read())
    resp.headers['Content-Type']        = 'application/pdf'
    resp.headers['Content-Disposition'] = \
        f'attachment; filename="aurum_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf"'
    return resp


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
