from flask import Flask, render_template, redirect, url_for, session, request, flash, make_response
import psycopg2
import psycopg2.extras
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from datetime import datetime, timedelta
import re

import pdfplumber
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph, Frame

from werkzeug.security import check_password_hash, generate_password_hash

from dotenv import load_dotenv
import os
import secrets
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB, limite de upload do comprovante

@app.template_filter('brl')
def brl_filter(value):
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user':   os.getenv('DB_USER'),
    'password': os.getenv('DB_PASS'),
    'host':   os.getenv('DB_HOST', 'localhost'),
    'port':   int(os.getenv('DB_PORT', '5432')),
}

SMTP_HOST    = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT    = int(os.getenv('SMTP_PORT', '587'))
SMTP_USUARIO = os.getenv('SMTP_USUARIO')
SMTP_SENHA   = os.getenv('SMTP_SENHA')
APP_ENV      = os.getenv('APP_ENV', 'producao')


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


# ── COMPROVANTES: extração de dados a partir de PDF compartilhado ──────────────

MESES = {'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4, 'maio': 5,
         'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10,
         'novembro': 11, 'dezembro': 12}


def _normaliza_valor_br(raw):
    """'1.234,56' -> 1234.56 ; '131' -> 131.0 ; devolve float ou None."""
    raw = raw.strip()
    if ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif re.match(r'^\d{1,3}\.\d{3}$', raw):        # 1.200 (milhar) -> 1200
        raw = raw.replace('.', '')
    try:
        return float(raw)
    except ValueError:
        return None


def _extrair_comprovante(texto):
    # valor: prefere "total"/"valor"; senão o primeiro R$ (centavos opcionais)
    valor = None
    for chave in ('total', 'valor'):
        m = re.search(rf'{chave}[^\n]{{0,20}}?R\$\s*([\d.]{{1,12}}(?:,\d{{2}})?)', texto, re.IGNORECASE)
        if m:
            valor = m.group(1)
            break
    if valor is None:
        m = re.search(r'R\$\s*([\d.]{1,12}(?:,\d{2})?)', texto)
        if m:
            valor = m.group(1)
    if valor is not None:
        v = _normaliza_valor_br(valor)
        valor = f'{v:.2f}' if v is not None else None

    # data: dd/mm/aaaa, dd-mm-aaaa, ou "DD de mês de AAAA"; senão hoje
    data_lancamento = None
    m = re.search(r'(\d{2})[/-](\d{2})[/-](\d{4})', texto)
    if m:
        dia, mes, ano = m.groups()
        data_lancamento = f'{ano}-{mes}-{dia}'
    else:
        m = re.search(r'(\d{1,2})\s+de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})', texto)
        if m and m.group(2).lower() in MESES:
            data_lancamento = f'{m.group(3)}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}'
    if not data_lancamento:
        data_lancamento = datetime.now().strftime('%Y-%m-%d')

    texto_lower = texto.lower()
    if 'pix' in texto_lower:
        rotulo = 'Pagamento PIX'
    elif 'boleto' in texto_lower:
        rotulo = 'Pagamento de boleto'
    else:
        rotulo = 'Comprovante de pagamento'

    descricao = rotulo
    for chave in ('favorecido', 'beneficiário', 'beneficiario', 'recebedor', 'para'):
        m = re.search(rf'{chave}\s*[:\-]?\s*([^\n]{{3,60}})', texto, re.IGNORECASE)
        if m:
            nome = m.group(1).strip(' -:')
            if nome:
                descricao = f'{rotulo}: {nome}'
                break

    return {
        'descricao': descricao,
        'data_lancamento': data_lancamento,
        'valor': valor or '',
        'tipo_lancamento': 'despesa',
        'situacao': 'ativo',
        'observacao': ' '.join(texto.split())[:140],
        'valor_encontrado': valor is not None,
    }


def _extrair_extrato_geometria(pdf):
    """Formato Mercado Pago: datas com hífen, descrição pode ocupar 2-3 linhas
    acima/abaixo da linha da transação. Usa a posição (x/y) das palavras para
    atribuir cada pedaço de descrição à transação verticalmente mais próxima."""
    itens = []
    for page in pdf.pages:
        words = page.extract_words(x_tolerance=1.5)

        # âncoras = datas na coluna "Data" (x0 pequeno)
        anchors = [{'top': w['top'], 'date': w['text'], 'desc': [], 'val': []}
                   for w in words
                   if w['x0'] < 88 and re.match(r'^\d{2}-\d{2}-\d{4}$', w['text'])]
        if not anchors:
            continue

        def mais_proxima(w):
            return min(anchors, key=lambda a: abs(a['top'] - w['top']))

        for w in words:
            if 85 <= w['x0'] < 196:                         # coluna Descrição
                a = mais_proxima(w)
                if abs(a['top'] - w['top']) <= 18:
                    a['desc'].append(w)
            elif 285 <= w['x0'] < 362:                      # coluna Valor
                a = mais_proxima(w)
                if abs(a['top'] - w['top']) <= 6:
                    a['val'].append(w)

        for a in anchors:
            desc = ' '.join(x['text'] for x in sorted(a['desc'], key=lambda x: (round(x['top']), x['x0']))).strip()
            valtxt = ' '.join(x['text'] for x in sorted(a['val'], key=lambda x: x['x0']))
            mv = re.search(r'(-?)\s*([\d.]+,\d{2})', valtxt)
            if not desc or not mv:
                continue
            v = _normaliza_valor_br(mv.group(2))
            if v is None:
                continue
            dia, mes, ano = a['date'].split('-')
            itens.append({
                'descricao': desc[:255],
                'data_lancamento': f'{ano}-{mes}-{dia}',
                'valor': f'{v:.2f}',
                'tipo_lancamento': 'despesa' if mv.group(1) == '-' else 'receita',
            })
    return itens


LINHA_EXTRATO = re.compile(
    r'^(\d{2})/(\d{2})/(\d{4})\s+(.+?)\s+(-?[\d.]+,\d{2})\s+[\d.]+,\d{2}\s*$'
)
DOC_CODIGO = re.compile(r'^([A-Z]{2,5}\d{4,}|PIX_[A-Z]+|\d{5,})$')


def _extrair_extrato_linhas(texto):
    """Formato uma-linha-por-transação (ex.: Sicredi): 'dd/mm/aaaa descrição
    [documento] valor saldo' em uma única linha por lançamento."""
    itens = []
    for linha in texto.splitlines():
        m = LINHA_EXTRATO.match(linha.strip())
        if not m:
            continue
        dia, mes, ano, resto, valor_raw = m.groups()
        v = _normaliza_valor_br(valor_raw.lstrip('-'))
        if v is None:
            continue

        partes = resto.split()
        if partes and DOC_CODIGO.match(partes[-1]):
            partes = partes[:-1]
        desc = ' '.join(partes).strip(' .-') or resto.strip()

        itens.append({
            'descricao': desc[:255],
            'data_lancamento': f'{ano}-{mes}-{dia}',
            'valor': f'{v:.2f}',
            'tipo_lancamento': 'despesa' if valor_raw.strip().startswith('-') else 'receita',
        })
    return itens


def _extrair_extrato(pdf):
    """Tenta os parsers de extrato conhecidos e devolve o que achar mais transações."""
    itens_geo = _extrair_extrato_geometria(pdf)

    texto = ''.join((p.extract_text() or '') + '\n' for p in pdf.pages)
    itens_linha = _extrair_extrato_linhas(texto)

    return itens_geo if len(itens_geo) >= len(itens_linha) else itens_linha


# ── CHAT: interpreta uma frase em linguagem natural (parser por regras, local) ──

RECEITA_KW = ('recebi', 'ganhei', 'salário', 'salario', 'entrou', 'vendi',
              'rendimento', 'depósito', 'deposito', 'freela', 'renda',
              'reembolso', 'restituição', 'restituicao')
DESPESA_KW = ('gastei', 'paguei', 'comprei', 'gasto', 'débito', 'debito',
              'saída', 'saida', 'boleto', 'conta')


def _interpretar_texto(texto):
    t   = texto.strip()
    low = t.lower()

    # valor: primeiro número (aceita R$, milhar com ponto e decimal com vírgula)
    valor = None
    m = re.search(r'(?:r\$\s*)?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)', low)
    if m:
        raw = m.group(1)
        if '.' in raw and ',' in raw:
            raw = raw.replace('.', '').replace(',', '.')        # 1.200,50 -> 1200.50
        elif ',' in raw:
            raw = raw.replace(',', '.')                          # 89,90 -> 89.90
        elif re.match(r'^\d{1,3}\.\d{3}$', raw):
            raw = raw.replace('.', '')                           # 1.200 -> 1200
        try:
            valor = f'{float(raw):.2f}'
        except ValueError:
            valor = None

    # tipo: sinal explícito ou palavras-chave; default despesa
    tipo = 'despesa'
    if t.lstrip().startswith('+') or any(k in low for k in RECEITA_KW):
        tipo = 'receita'
    if t.lstrip().startswith('-') or any(k in low for k in DESPESA_KW):
        tipo = 'despesa'

    # data: hoje/ontem/anteontem/"dia N[/M]"; default hoje
    hoje = datetime.now().date()
    data = hoje
    if 'anteontem' in low:
        data = hoje - timedelta(days=2)
    elif 'ontem' in low:
        data = hoje - timedelta(days=1)
    else:
        md = re.search(r'dia\s+(\d{1,2})(?:/(\d{1,2}))?', low)
        if md:
            dia = int(md.group(1))
            mes = int(md.group(2)) if md.group(2) else hoje.month
            try:
                data = hoje.replace(day=dia, month=mes)
            except ValueError:
                data = hoje

    # descrição: remove valor, verbos, marcadores de data e preposição inicial
    desc = t
    if m:
        desc = desc.replace(m.group(0), ' ')
    desc = re.sub(r'(?i)\b(r\$|reais|hoje|ontem|anteontem|gastei|paguei|comprei|'
                  r'recebi|ganhei|vendi)\b', ' ', desc)
    desc = re.sub(r'(?i)\bdia\s+\d{1,2}(?:/\d{1,2})?\b', ' ', desc)
    desc = re.sub(r'(?i)^[\s\-+]*(no|na|em|com|de|do|da|para|pra|o|a)\b', ' ', desc)
    desc = re.sub(r'\s+', ' ', desc).strip(' -+.,')
    desc = (desc[0].upper() + desc[1:]) if desc else 'Lançamento'

    return {
        'descricao': desc,
        'data_lancamento': data.strftime('%Y-%m-%d'),
        'valor': valor or '',
        'tipo_lancamento': tipo,
        'situacao': 'ativo',
        'observacao': t[:140],
        'valor_encontrado': valor is not None,
    }


def _email_html(acao, campos):
    if acao == 'criado':
        cor_acao, label_acao = '#4caf7d', 'Novo Lançamento'
    elif acao == 'excluido':
        cor_acao, label_acao = '#c97a7a', 'Lançamento Excluído'
    else:
        cor_acao, label_acao = '#00FF4E', 'Lançamento Atualizado'
    tipo       = campos.get('tipo_lancamento', '')
    cor_tipo   = '#4caf7d' if tipo == 'receita' else '#c97a7a'
    valor_fmt  = f"R$ {float(campos.get('valor', 0)):,.2f}".replace(',','X').replace('.',',').replace('X','.')

    def row(label, valor, cor='#FFFFFF'):
        return (
            '<tr>'
            f'<td style="padding:10px 0;border-bottom:1px solid #333333;font-size:10px;'
            f'letter-spacing:.15em;text-transform:uppercase;color:#8a8a8a;width:36%;">{label}</td>'
            f'<td style="padding:10px 0;border-bottom:1px solid #333333;font-size:13px;'
            f'color:{cor};font-family:\'Courier New\',monospace;">{valor}</td>'
            '</tr>'
        )

    rows = (
          row('ID',        f"#{campos.get('id', '·')}")
        + row('Descrição', campos.get('descricao', ''))
        + row('Data',      campos.get('data_lancamento', ''))
        + row('Tipo',      tipo.capitalize(), cor_tipo)
        + row('Valor',     valor_fmt, cor_tipo)
        + row('Situação',  campos.get('situacao', '').capitalize())
    )

    banner_homolog = (
        '<tr><td style="background:#7a5c00;padding:10px 36px;font-size:10px;letter-spacing:.18em;'
        'text-transform:uppercase;color:#ffe082;text-align:center;">'
        '&#9888; AMBIENTE DE HOMOLOGA&Ccedil;&Atilde;O: este e-mail n&atilde;o &eacute; real'
        '</td></tr>'
    ) if APP_ENV != 'producao' else ''

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#000000;font-family:'Courier New',Courier,monospace;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#000000;padding:40px 0;">
<tr><td align="center">
<table width="540" cellpadding="0" cellspacing="0"
       style="background:#242424;border:1px solid #333333;max-width:540px;width:100%;">

  {banner_homolog}
  <tr><td style="height:2px;background:linear-gradient(90deg,transparent,#00FF4E,transparent);font-size:0;">&nbsp;</td></tr>

  <tr>
    <td style="padding:32px 36px 24px;border-bottom:1px solid #333333;">
      <span style="font-size:22px;color:#00FF4E;font-family:Georgia,serif;font-weight:700;">&#9670;</span>
      <span style="font-size:14px;color:#FFFFFF;font-family:Georgia,serif;
                   letter-spacing:.28em;text-transform:uppercase;margin-left:8px;">BAHGOAL</span>
      <p style="margin:10px 0 0;font-size:9px;letter-spacing:.22em;
                text-transform:uppercase;color:#8a8a8a;">Força. Velocidade. Liberdade.</p>
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
    <td style="padding:18px 36px 24px;border-top:1px solid #333333;">
      <p style="margin:0;font-size:9px;letter-spacing:.15em;
                text-transform:uppercase;color:#8a8a8a;">
        {datetime.now().strftime('%d/%m/%Y às %H:%M')} &nbsp;·&nbsp; Bahgoal
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
        prefixo = '[HOMOLOG] ' if APP_ENV != 'producao' else ''
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'{prefixo}{assunto}'
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


# ── LANÇAMENTOS: helpers compartilhados ─────────────────────────────────────────

def _ler_filtros():
    return {
        'tipo':     request.args.get('tipo', ''),
        'situacao': request.args.get('situacao', ''),
        'data_ini': request.args.get('data_ini', ''),
        'data_fim': request.args.get('data_fim', ''),
    }


def _buscar_lancamentos(filtros):
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query, params = "SELECT * FROM lancamento WHERE 1=1", []
    if filtros['tipo']:
        query += " AND tipo_lancamento = %s"
        params.append(filtros['tipo'])
    if filtros['situacao']:
        query += " AND situacao = %s"
        params.append(filtros['situacao'])
    if filtros['data_ini']:
        query += " AND data_lancamento >= %s"
        params.append(filtros['data_ini'])
    if filtros['data_fim']:
        query += " AND data_lancamento <= %s"
        params.append(filtros['data_fim'])
    query += " ORDER BY data_lancamento DESC"

    cur.execute(query, params)
    registros = cur.fetchall()
    cur.close()
    conn.close()
    return registros


def _calcular_totais(registros):
    ativos         = [r for r in registros if r['situacao'] == 'ativo']
    total_receitas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'receita')
    total_despesas = sum(r['valor'] for r in ativos if r['tipo_lancamento'] == 'despesa')
    return total_receitas, total_despesas, total_receitas - total_despesas


# ── HOME: metas e insights ──────────────────────────────────────────────────────

def _progresso_metas(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM meta WHERE situacao = 'ativo' ORDER BY id DESC")
    metas = cur.fetchall()

    hoje = datetime.now().date()
    resultado = []
    for m in metas:
        alvo = float(m['valor_alvo'])
        if m['tipo'] == 'limite':
            cur.execute(
                """SELECT COALESCE(SUM(valor), 0) FROM lancamento
                   WHERE tipo_lancamento = 'despesa' AND situacao = 'ativo'
                     AND date_trunc('month', data_lancamento) = date_trunc('month', CURRENT_DATE)"""
            )
            progresso = float(cur.fetchone()[0])
            pct    = min(progresso / alvo * 100, 999) if alvo else 0
            status = 'estourou' if pct >= 100 else ('atencao' if pct >= 80 else 'ok')
            resultado.append({
                'id': m['id'], 'nome': m['nome'], 'tipo': 'limite',
                'valor_alvo': alvo, 'progresso': progresso, 'pct': round(pct),
                'status': status, 'data_alvo': None, 'dias_restantes': None,
            })
        else:
            cur.execute(
                """SELECT COALESCE(SUM(CASE WHEN tipo_lancamento = 'receita' THEN valor ELSE -valor END), 0)
                   FROM lancamento WHERE situacao = 'ativo' AND data_lancamento >= %s""",
                (m['data_inicio'],)
            )
            progresso = max(float(cur.fetchone()[0]), 0)
            pct    = min(progresso / alvo * 100, 999) if alvo else 0
            status = 'ok' if pct >= 100 else ('atencao' if pct >= 50 else 'inicio')
            dias_restantes = (m['data_alvo'] - hoje).days if m['data_alvo'] else None
            resultado.append({
                'id': m['id'], 'nome': m['nome'], 'tipo': 'economia',
                'valor_alvo': alvo, 'progresso': progresso, 'pct': round(pct),
                'status': status, 'data_alvo': m['data_alvo'], 'dias_restantes': dias_restantes,
            })
    cur.close()
    return resultado


def _calcular_insights(conn):
    cur = conn.cursor()
    hoje = datetime.now().date()
    primeiro_dia_mes = hoje.replace(day=1)
    if primeiro_dia_mes.month == 1:
        primeiro_dia_mes_ant = primeiro_dia_mes.replace(year=primeiro_dia_mes.year - 1, month=12)
    else:
        primeiro_dia_mes_ant = primeiro_dia_mes.replace(month=primeiro_dia_mes.month - 1)
    ultimo_dia_mes_ant = primeiro_dia_mes - timedelta(days=1)

    cur.execute(
        """SELECT COALESCE(SUM(valor), 0) FROM lancamento
           WHERE tipo_lancamento = 'despesa' AND situacao = 'ativo' AND data_lancamento >= %s""",
        (primeiro_dia_mes,)
    )
    despesas_mes_atual = float(cur.fetchone()[0])

    cur.execute(
        """SELECT COALESCE(SUM(valor), 0) FROM lancamento
           WHERE tipo_lancamento = 'despesa' AND situacao = 'ativo'
             AND data_lancamento BETWEEN %s AND %s""",
        (primeiro_dia_mes_ant, ultimo_dia_mes_ant)
    )
    despesas_mes_passado = float(cur.fetchone()[0])

    variacao_pct = (
        round((despesas_mes_atual - despesas_mes_passado) / despesas_mes_passado * 100)
        if despesas_mes_passado > 0 else None
    )

    cur.execute(
        """SELECT descricao, valor FROM lancamento
           WHERE tipo_lancamento = 'despesa' AND situacao = 'ativo' AND data_lancamento >= %s
           ORDER BY valor DESC LIMIT 1""",
        (primeiro_dia_mes,)
    )
    maior = cur.fetchone()
    maior_gasto = {'descricao': maior[0], 'valor': float(maior[1])} if maior else None

    dias_passados = (hoje - primeiro_dia_mes).days + 1
    if hoje.month == 12:
        proximo_mes = hoje.replace(year=hoje.year + 1, month=1, day=1)
    else:
        proximo_mes = hoje.replace(month=hoje.month + 1, day=1)
    dias_no_mes = (proximo_mes - primeiro_dia_mes).days
    projecao = (despesas_mes_atual / dias_passados * dias_no_mes) if dias_passados else 0.0

    cur.close()
    return {
        'despesas_mes_atual':   despesas_mes_atual,
        'despesas_mes_passado': despesas_mes_passado,
        'variacao_pct':         variacao_pct,
        'maior_gasto':          maior_gasto,
        'projecao':             projecao,
        'dias_passados':        dias_passados,
        'dias_no_mes':          dias_no_mes,
    }


@app.route('/home')
@login_required
def home():
    conn = get_conn()
    try:
        metas    = _progresso_metas(conn)
        insights = _calcular_insights(conn)
    finally:
        conn.close()

    return render_template('home.html',
                           usuario_nome=session.get('usuario_nome'),
                           metas=metas,
                           insights=insights,
                           draft=session.get('chat_draft'),
                           msg=session.get('chat_msg'),
                           erro=session.get('chat_erro'),
                           chat_origem=session.get('chat_origem', 'home'))


@app.route('/metas/nova', methods=['POST'])
@login_required
def metas_nova():
    nome       = request.form.get('nome', '').strip()
    tipo       = request.form.get('tipo', '')
    valor_alvo = request.form.get('valor_alvo', '').replace(',', '.')
    data_alvo  = request.form.get('data_alvo') or None

    if not nome or tipo not in ('limite', 'economia') or not valor_alvo:
        flash('Preencha nome, tipo e valor da meta.', 'erro')
        return redirect(url_for('home'))

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO meta (nome, tipo, valor_alvo, data_alvo) VALUES (%s, %s, %s, %s)",
            (nome, tipo, float(valor_alvo), data_alvo)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash('Meta criada.', 'ok')
    except Exception as e:
        flash(f'Erro ao criar meta: {e}', 'erro')
    return redirect(url_for('home'))


@app.route('/metas/excluir/<int:id>', methods=['POST'])
@login_required
def metas_excluir(id):
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("DELETE FROM meta WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        flash('Meta removida.', 'ok')
    except Exception as e:
        flash(f'Erro ao remover meta: {e}', 'erro')
    return redirect(url_for('home'))


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
                "SELECT * FROM usuario WHERE login = %s AND situacao = 'ativo'",
                (login_input,)
            )
            usuario = cur.fetchone()
            cur.close()
            conn.close()
            if usuario and check_password_hash(usuario['senha'], senha_input):
                session['usuario_id']    = usuario['id']
                session['usuario_nome']  = usuario['nome']
                email_usuario = usuario['email'] or ''
                # Admin sem e-mail cadastrado usa a própria conta SMTP (secrets) como destinatário
                if not email_usuario and usuario['login'] == 'admin':
                    email_usuario = SMTP_USUARIO or ''
                session['usuario_email'] = email_usuario
                return redirect(url_for('home'))
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
            cur.close()
            conn.close()
            session['usuario_email'] = email
            ok = 'E-mail atualizado com sucesso.'
        except Exception as e:
            erro = f'Erro ao salvar: {e}'

    return render_template('perfil.html',
                           usuario_nome=session.get('usuario_nome'),
                           usuario_email=session.get('usuario_email', ''),
                           erro=erro, ok=ok)


@app.route('/perfil/senha', methods=['POST'])
@login_required
def alterar_senha():
    atual    = request.form.get('senha_atual', '')
    nova     = request.form.get('senha_nova', '')
    confirma = request.form.get('senha_confirma', '')
    ok_senha = None
    erro_senha = None
    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT senha FROM usuario WHERE id = %s", (session['usuario_id'],))
        row = cur.fetchone()

        if not row or not check_password_hash(row['senha'], atual):
            erro_senha = 'Senha atual incorreta.'
        elif len(nova) < 6:
            erro_senha = 'A nova senha deve ter ao menos 6 caracteres.'
        elif nova != confirma:
            erro_senha = 'A confirmação não corresponde à nova senha.'
        else:
            cur.execute("UPDATE usuario SET senha = %s WHERE id = %s",
                        (generate_password_hash(nova), session['usuario_id']))
            conn.commit()
            ok_senha = 'Senha alterada com sucesso.'

        cur.close()
        conn.close()
    except Exception as e:
        erro_senha = f'Erro ao alterar a senha: {e}'

    return render_template('perfil.html',
                           usuario_nome=session.get('usuario_nome'),
                           usuario_email=session.get('usuario_email', ''),
                           erro=None, ok=None,
                           erro_senha=erro_senha, ok_senha=ok_senha)


# ── CHAT: registro de lançamento por linguagem natural ─────────────────────────

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'POST':
        texto  = request.form.get('mensagem', '').strip()
        origem = request.form.get('origem', 'chat')
        if texto:
            dados = _interpretar_texto(texto)
            session['chat_msg']    = texto
            session['chat_origem'] = origem
            if dados['valor_encontrado']:
                session['chat_draft'] = dados
                session.pop('chat_erro', None)
            else:
                session.pop('chat_draft', None)
                session['chat_erro'] = ('Não identifiquei o valor. Tente algo como '
                                        '"gastei 50 no mercado" ou "recebi 3000 de salário".')
        return redirect(url_for('home' if origem == 'home' else 'chat'))

    return render_template('chat.html',
                           draft=session.get('chat_draft'),
                           msg=session.get('chat_msg'),
                           erro=session.get('chat_erro'),
                           chat_origem=session.get('chat_origem', 'chat'),
                           usuario_nome=session.get('usuario_nome'))


@app.route('/chat/confirmar', methods=['POST'])
@login_required
def chat_confirmar():
    origem          = request.form.get('origem', 'chat')
    destino_erro    = 'home' if origem == 'home' else 'chat'
    descricao       = request.form.get('descricao', '').strip()
    data_lancamento = request.form.get('data_lancamento', '')
    valor           = request.form.get('valor', '').replace(',', '.')
    tipo_lancamento = request.form.get('tipo_lancamento', '')
    observacao      = request.form.get('observacao', '').strip()

    if not all([descricao, data_lancamento, valor, tipo_lancamento]):
        session['chat_erro'] = 'Faltou algum dado pra registrar o lançamento.'
        return redirect(url_for(destino_erro))

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao, observacao)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (descricao, data_lancamento, float(valor), tipo_lancamento, 'ativo', observacao)
        )
        novo_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        for k in ('chat_draft', 'chat_msg', 'chat_erro', 'chat_origem'):
            session.pop(k, None)

        flash('Lançamento registrado pelo chat.', 'ok')
        enviar_email(
            assunto=f'[Bahgoal] Novo lançamento: {descricao}',
            campos=dict(id=novo_id, descricao=descricao, data_lancamento=data_lancamento,
                        valor=valor, tipo_lancamento=tipo_lancamento, situacao='ativo', observacao=observacao),
            acao='criado',
            email_destinatario=session.get('usuario_email', ''),
        )
        return redirect(url_for('home' if origem == 'home' else 'lancamentos'))
    except Exception as e:
        session['chat_erro'] = f'Erro ao salvar: {e}'
        return redirect(url_for(destino_erro))


@app.route('/chat/descartar', methods=['POST'])
@login_required
def chat_descartar():
    origem = request.form.get('origem', 'chat')
    for k in ('chat_draft', 'chat_msg', 'chat_erro', 'chat_origem'):
        session.pop(k, None)
    return redirect(url_for('home' if origem == 'home' else 'chat'))


# ── LISTAR ─────────────────────────────────────────────────────────────────────

@app.route('/lancamentos')
@login_required
def lancamentos():
    filtros = _ler_filtros()

    try:
        registros = _buscar_lancamentos(filtros)
        total_receitas, total_despesas, saldo = _calcular_totais(registros)
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
        filtro_tipo=filtros['tipo'],
        filtro_situacao=filtros['situacao'],
        filtro_data_ini=filtros['data_ini'],
        filtro_data_fim=filtros['data_fim'],
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
        observacao      = request.form.get('observacao', '').strip()

        if not all([descricao, data_lancamento, valor, tipo_lancamento]):
            erro = 'Preencha todos os campos obrigatórios.'
        else:
            try:
                conn = get_conn()
                cur  = conn.cursor()
                cur.execute(
                    """INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao, observacao)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (descricao, data_lancamento, float(valor), tipo_lancamento, situacao, observacao)
                )
                novo_id = cur.fetchone()[0]
                conn.commit()
                cur.close()
                conn.close()

                flash('Lançamento criado com sucesso.', 'ok')
                enviar_email(
                    assunto=f'[Bahgoal] Novo lançamento: {descricao}',
                    campos=dict(id=novo_id, descricao=descricao, data_lancamento=data_lancamento,
                                valor=valor, tipo_lancamento=tipo_lancamento, situacao=situacao, observacao=observacao),
                    acao='criado',
                    email_destinatario=session.get('usuario_email', ''),
                )
                return redirect(url_for('lancamentos'))
            except Exception as e:
                erro = f'Erro ao salvar: {e}'

    prefill = session.pop('prefill', None) if request.method == 'GET' else None
    return render_template('form_lancamento.html', acao='Novo', lancamento=None, prefill=prefill,
                           erro=erro, usuario_nome=session.get('usuario_nome'))


# ── COMPARTILHAR: recebe comprovante via Web Share Target e pré-preenche ───────

@app.route('/compartilhar', methods=['POST'])
@login_required
def compartilhar():
    arquivo = request.files.get('comprovante')

    if not arquivo or arquivo.mimetype != 'application/pdf':
        flash('Não consegui ler o comprovante compartilhado. Preencha manualmente.', 'erro')
        return redirect(url_for('novo_lancamento'))

    try:
        with pdfplumber.open(BytesIO(arquivo.read())) as pdf:
            # Extrato (várias transações)? Se sim, vai pra tela de importação.
            itens = _extrair_extrato(pdf)
            if len(itens) >= 2:
                session['extrato'] = itens
                return redirect(url_for('importar_extrato'))

            # Senão, trata como comprovante de uma transação (pré-preenche o form).
            texto = ''.join((pagina.extract_text() or '') + '\n' for pagina in pdf.pages)

        dados = _extrair_comprovante(texto)
        if not dados['valor_encontrado']:
            flash('Não encontrei o valor no comprovante. Confira os campos antes de salvar.', 'erro')
        dados.pop('valor_encontrado')
        session['prefill'] = dados
    except Exception:
        flash('Não consegui ler o comprovante compartilhado. Preencha manualmente.', 'erro')

    return redirect(url_for('novo_lancamento'))


@app.route('/importar', methods=['GET', 'POST'])
@login_required
def importar_extrato():
    itens = session.get('extrato')
    if not itens:
        return redirect(url_for('lancamentos'))

    if request.method == 'POST':
        selecionados = request.form.getlist('sel')
        indices = {int(i) for i in selecionados if i.isdigit()}
        escolhidos = [it for n, it in enumerate(itens) if n in indices]

        if not escolhidos:
            flash('Nenhuma transação selecionada.', 'erro')
            return redirect(url_for('importar_extrato'))

        try:
            conn = get_conn()
            cur  = conn.cursor()

            # deduplicação: ignora transações já existentes (mesma data+valor+tipo+descrição)
            cur.execute("SELECT descricao, data_lancamento, valor, tipo_lancamento FROM lancamento")
            existentes = {(d, str(dt), float(v), t) for (d, dt, v, t) in cur.fetchall()}

            novos = []
            for it in escolhidos:
                chave = (it['descricao'], it['data_lancamento'], float(it['valor']), it['tipo_lancamento'])
                if chave not in existentes:
                    novos.append(it)
                    existentes.add(chave)          # evita duplicar dentro do próprio lote

            if novos:
                cur.executemany(
                    """INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao, observacao)
                       VALUES (%s, %s, %s, %s, 'ativo', %s)""",
                    [(it['descricao'], it['data_lancamento'], float(it['valor']),
                      it['tipo_lancamento'], 'Importado do extrato') for it in novos]
                )
                conn.commit()
            cur.close()
            conn.close()
            session.pop('extrato', None)

            dup = len(escolhidos) - len(novos)
            if not novos:
                flash(f'As {len(escolhidos)} transações selecionadas já haviam sido importadas.', 'erro')
            elif dup:
                flash(f'{len(novos)} lançamento(s) importado(s) · {dup} já existiam (ignorados).', 'ok')
            else:
                flash(f'{len(novos)} lançamento(s) importado(s) do extrato.', 'ok')
            return redirect(url_for('lancamentos'))
        except Exception as e:
            flash(f'Erro ao importar: {e}', 'erro')
            return redirect(url_for('importar_extrato'))

    total_rec = sum(1 for it in itens if it['tipo_lancamento'] == 'receita')
    return render_template('importar.html', itens=itens,
                           total=len(itens), total_rec=total_rec, total_desp=len(itens) - total_rec,
                           usuario_nome=session.get('usuario_nome'))


@app.route('/importar/descartar', methods=['POST'])
@login_required
def importar_descartar():
    session.pop('extrato', None)
    return redirect(url_for('lancamentos'))


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
        observacao      = request.form.get('observacao', '')

        if not all([descricao, data_lancamento, valor, tipo_lancamento]):
            erro = 'Preencha todos os campos obrigatórios.'
        else:
            try:
                cur.execute(
                    """UPDATE lancamento
                       SET descricao=%s, data_lancamento=%s, valor=%s,
                           tipo_lancamento=%s, situacao=%s, observacao=%s
                       WHERE id=%s""",
                    (descricao, data_lancamento, float(valor), tipo_lancamento, situacao, observacao, id)
                )
                conn.commit()
                cur.close()
                conn.close()

                flash('Lançamento atualizado.', 'ok')
                enviar_email(
                    assunto=f'[Bahgoal] Lançamento atualizado: {descricao}',
                    campos=dict(id=id, descricao=descricao, data_lancamento=data_lancamento,
                                valor=valor, tipo_lancamento=tipo_lancamento, situacao=situacao, observacao=observacao),
                    acao='atualizado',
                    email_destinatario=session.get('usuario_email', ''),
                )
                return redirect(url_for('lancamentos'))
            except Exception as e:
                erro = f'Erro ao atualizar: {e}'

    cur.execute("SELECT * FROM lancamento WHERE id = %s", (id,))
    lancamento = cur.fetchone()
    cur.close()
    conn.close()

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
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM lancamento WHERE id = %s", (id,))
        lancamento = cur.fetchone()
        cur.execute("DELETE FROM lancamento WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        flash('Lançamento excluído.', 'ok')
        if lancamento:
            enviar_email(
                assunto=f'[Bahgoal] Lançamento excluído: {lancamento["descricao"]}',
                campos=dict(id=id, descricao=lancamento['descricao'],
                            data_lancamento=lancamento['data_lancamento'],
                            valor=lancamento['valor'],
                            tipo_lancamento=lancamento['tipo_lancamento'],
                            situacao=lancamento['situacao'], observacao=lancamento.get('observacao', '')),
                acao='excluido',
                email_destinatario=session.get('usuario_email', ''),
            )
    except Exception as e:
        flash(f'Erro ao excluir: {e}', 'erro')
    return redirect(url_for('lancamentos'))


# ── EXPORTAR PDF ───────────────────────────────────────────────────────────────

@app.route('/lancamentos/exportar-pdf')
@login_required
def exportar_pdf():
    filtros   = _ler_filtros()
    registros = _buscar_lancamentos(filtros)
    total_receitas, total_despesas, saldo = _calcular_totais(registros)

    GOLD    = colors.HexColor('#00FF4E')
    DARK    = colors.HexColor('#000000')
    SURFACE = colors.HexColor('#242424')
    SURFACE2= colors.HexColor('#1a1a1a')
    GREEN   = colors.HexColor('#4caf7d')
    RED     = colors.HexColor('#c97a7a')
    MUTED   = colors.HexColor('#8a8a8a')
    TEXT    = colors.HexColor('#FFFFFF')
    BORDER  = colors.HexColor('#333333')

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
        c.drawString(M, PAGE_H - 18 * mm, 'BAHGOAL')

        c.setFont('Helvetica', 8)
        c.setFillColor(MUTED)
        c.drawString(M, PAGE_H - 23 * mm, 'FORCA. VELOCIDADE. LIBERDADE.')
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
        c.drawString(M, footer_y, 'BAHGOAL')
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
                   None if r['situacao'] == 'ativo' else '#8a8a8a'),
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
        f'attachment; filename="bahgoal_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf"'
    return resp

if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=5000, debug=debug)
