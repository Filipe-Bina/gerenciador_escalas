import os
import json
import datetime
from calendar import monthrange
from urllib import request as urllib_request
from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_secreta_fallback')

# ============================================ VERIFICAÇÃO DA VARIÁVEL DATABASE_URL ============================================
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    print("⚠️ AVISO: DATABASE_URL não está configurada!")
    print("   Configure a variável DATABASE_URL nas variáveis de ambiente do Render")
    print("   Exemplo: postgres://user:pass@host:port/database")

# Lista de admins (em produção, use banco de dados)
ADMIN_USERS = {
    "admin1": "senha123",
    "admin2": "senha456"
}

FERIADOS_API_URL = "https://brasilapi.com.br/api/feriados/v1/{ano}?estado=SP"
FERIADOS_HEADERS = {"User-Agent": "Mozilla/5.0"}
SP_STATE_HOLIDAYS = {
    2026: {"2026-07-09"},
}


def parse_holiday_payload(payload):
    return {item.get("date") for item in payload if isinstance(item, dict) and item.get("date")}


def fetch_public_holidays(ano):
    req = urllib_request.Request(
        FERIADOS_API_URL.format(ano=ano),
        headers=FERIADOS_HEADERS,
    )

    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return set()

    return parse_holiday_payload(payload)


def load_school_holidays(ano):
    valor = os.environ.get("SP_SCHOOL_HOLIDAYS", "")
    if not valor:
        return set()

    return {item.strip() for item in valor.split(",") if item.strip() and item.strip().startswith(f"{ano}-")}


def load_manual_holidays_for_year(ano):
    try:
        init_db()
    except Exception:
        return set()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT data FROM feriados_manuais WHERE EXTRACT(YEAR FROM data) = %s",
        (ano,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return {row["data"].strftime("%Y-%m-%d") for row in rows}


def load_holidays_for_year(ano):
    feriados = fetch_public_holidays(ano)
    feriados.update(SP_STATE_HOLIDAYS.get(ano, set()))
    feriados.update(load_school_holidays(ano))
    feriados.update(load_manual_holidays_for_year(ano))
    return feriados


def is_plantao_day(data, feriados=None):
    if feriados is None:
        feriados = load_holidays_for_year(data.year)

    data_str = data.strftime("%Y-%m-%d")
    return data.weekday() >= 5 or data_str in feriados


def load_inactive_tecnicos_for_period(start_date, end_date):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tecnico_re, data_inicio, data_fim FROM tecnico_inativo WHERE data_inicio <= %s AND data_fim >= %s",
        (end_date, start_date),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    inactive_by_date = {}
    for row in rows:
        current_date = row["data_inicio"]
        while current_date <= row["data_fim"]:
            inactive_by_date.setdefault(current_date.strftime("%Y-%m-%d"), set()).add(row["tecnico_re"])
            current_date += datetime.timedelta(days=1)

    return inactive_by_date


def load_previous_month_turn_counts(ano, mes):
    current_month = datetime.date(ano, mes, 1)
    previous_month = current_month.replace(month=current_month.month - 1) if current_month.month > 1 else current_month.replace(year=current_month.year - 1, month=12)
    previous_start = previous_month
    previous_end = previous_month.replace(day=monthrange(previous_month.year, previous_month.month)[1])

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tecnico_re, COUNT(*) FROM escala WHERE data BETWEEN %s AND %s GROUP BY tecnico_re",
        (previous_start.strftime("%Y-%m-%d"), previous_end.strftime("%Y-%m-%d")),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return dict(rows)


def resolve_dashboard_month():
    current_month = datetime.date.today().replace(day=1)
    ano_param = request.args.get('ano')
    mes_param = request.args.get('mes')

    try:
        return datetime.date(int(ano_param), int(mes_param), 1)
    except (TypeError, ValueError):
        return current_month


def resolve_dashboard_weekend_dates(selected_month, reference_date=None):
    if reference_date is None:
        reference_date = datetime.date.today()

    first_day = selected_month
    last_day = selected_month.replace(day=monthrange(selected_month.year, selected_month.month)[1])

    if selected_month.year == reference_date.year and selected_month.month == reference_date.month:
        days_until_saturday = (5 - reference_date.weekday()) % 7
        next_saturday = reference_date + datetime.timedelta(days=days_until_saturday)

        if next_saturday <= last_day:
            return next_saturday, next_saturday + datetime.timedelta(days=1)

        return None

    first_saturday = first_day + datetime.timedelta(days=(5 - first_day.weekday()) % 7)
    return first_saturday, first_saturday + datetime.timedelta(days=1)


def build_month_calendar_view(month_start, rows, holiday_dates=None):
    month_last_day = monthrange(month_start.year, month_start.month)[1]
    first_weekday = month_start.weekday()
    holiday_dates = holiday_dates or set()
    calendar_days = []

    for _ in range(first_weekday):
        calendar_days.append({"empty": True})

    entries_by_day = {}
    for row in rows:
        day = int(row['data_formatada'][:2])
        entries_by_day.setdefault(day, []).append({
            "area": row['area'],
            "turno": row['turno'],
            "tecnico_nome": row['tecnico_nome'],
            "tecnico_re": row['tecnico_re'],
        })

    for day in range(1, month_last_day + 1):
        date_obj = datetime.date(month_start.year, month_start.month, day)
        date_key = date_obj.isoformat()
        calendar_days.append({
            "day": day,
            "date": date_obj,
            "date_key": date_key,
            "is_weekend": date_obj.weekday() >= 5,
            "is_holiday": date_key in holiday_dates,
            "entries": entries_by_day.get(day, []),
            "empty": False,
        })

    return calendar_days


# Lista de técnicos por área
TECNICOS = [
    {"re": "30981", "nome": "ANDERSON PEDRO DE SOUZA", "area": "TAUBATE"},
    {"re": "32965", "nome": "FÁBIO APARECIDO ALVES", "area": "TAUBATE"},
    {"re": "34322", "nome": "JARY OLIVEIRA", "area": "TAUBATE"},
    {"re": "34020", "nome": "JOSÉ DIVINO LEOPOLDINO", "area": "TAUBATE"},
    {"re": "30116", "nome": "LUIZ RICARDO ALKIMIN", "area": "TAUBATE"},
    {"re": "34892", "nome": "RONALDO CAMPOS LEOPOLDO", "area": "TAUBATE"},
    {"re": "30498", "nome": "GUIDO FERREIRA SOBRINHO", "area": "TAUBATE"},
    {"re": "30602", "nome": "JOSÉ LUIZ RAIMUNDO", "area": "TAUBATE"},
    {"re": "30626", "nome": "JOSIMAR PAULO DE AZEVEDO", "area": "TAUBATE"},
    {"re": "33167", "nome": "SÉRGIO HENRIQUE DA SILVA", "area": "SJC"},
    {"re": "34298", "nome": "VANDERLEI DOS SANTOS", "area": "SJC"},
    {"re": "35383", "nome": "ANDERSON MOREIRA", "area": "SJC"},
    {"re": "31369", "nome": "SANTIAGO GUIZALBERTI", "area": "SJC"},
    {"re": "30641", "nome": "LEIF ERICKSON", "area": "SJC"},
    {"re": "35273", "nome": "RODRIGO SILVA", "area": "SJC"},
    {"re": "35476", "nome": "JULIARD TEIXEIRA BARBOSA", "area": "SJC"},
    {"re": "32989", "nome": "SILVIO TEIXEIRA DE PAIVA", "area": "SJC"},
    {"re": "34854", "nome": "LUCINEI CAMPOS", "area": "LITORAL"},
    {"re": "32626", "nome": "WANDERLEI RODRIGUES SOUZA", "area": "LITORAL"},
    {"re": "30930", "nome": "WILTON DIAS FERNANDES", "area": "LITORAL"},
    {"re": "32590", "nome": "RENILSON SANTANA DE OLIVEIRA", "area": "LITORAL"},
    {"re": "35384", "nome": "JEFERSON ANTUNES", "area": "LITORAL"}
]

def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não configurada! Configure no painel do Render.")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS escala (
            id SERIAL PRIMARY KEY,
            data DATE NOT NULL,
            area VARCHAR(50) NOT NULL,
            turno VARCHAR(50) NOT NULL,
            tecnico_re VARCHAR(20) NOT NULL,
            tecnico_nome VARCHAR(100) NOT NULL,
            UNIQUE(data, area, turno)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feriados_manuais (
            id SERIAL PRIMARY KEY,
            data DATE NOT NULL UNIQUE,
            descricao VARCHAR(200) NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tecnico_inativo (
            id SERIAL PRIMARY KEY,
            tecnico_re VARCHAR(20) NOT NULL,
            tecnico_nome VARCHAR(100) NOT NULL,
            data_inicio DATE NOT NULL,
            data_fim DATE NOT NULL,
            motivo VARCHAR(30) NOT NULL,
            UNIQUE(tecnico_re, data_inicio, data_fim, motivo)
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()


def obter_proximo_tecnico(area, contagem_turnos, tecnico_excluir=None, inactive_re=None, data=None, historico_turnos=None, peso_mes_anterior=2):
    """Retorna o técnico com menor carga balanceada, priorizando o histórico do mês anterior."""
    tecs_area = [t for t in TECNICOS if t['area'] == area]

    if tecnico_excluir:
        tecs_area = [t for t in tecs_area if t['re'] != tecnico_excluir]

    if inactive_re:
        tecs_area = [t for t in tecs_area if t['re'] not in inactive_re]

    if not tecs_area:
        return None

    historico_turnos = historico_turnos or {}

    def score(tecnico):
        atual = contagem_turnos.get(tecnico['re'], 0)
        historico = historico_turnos.get(tecnico['re'], 0)
        return atual + (historico * peso_mes_anterior)

    tecs_area.sort(key=score)
    return tecs_area[0]


def gerar_escala_automatica(ano, mes):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    primeiro_dia = f"{ano}-{mes:02d}-01"
    ultimo_dia = f"{ano}-{mes:02d}-{monthrange(ano, mes)[1]}"

    cursor.execute("DELETE FROM escala WHERE data BETWEEN %s AND %s", (primeiro_dia, ultimo_dia))

    historico_turnos = load_previous_month_turn_counts(ano, mes)
    contagem_turnos = {}

    num_dias = monthrange(ano, mes)[1]
    feriados_do_ano = load_holidays_for_year(ano)
    inactive_by_date = load_inactive_tecnicos_for_period(primeiro_dia, ultimo_dia)

    for dia in range(1, num_dias + 1):
        data_atual = datetime.date(ano, mes, dia)
        data_str = data_atual.strftime("%Y-%m-%d")
        inactive_re = inactive_by_date.get(data_str, set())

        is_plantao = is_plantao_day(data_atual, feriados_do_ano)

        if is_plantao:
            # SJC
            t1_sjc = obter_proximo_tecnico("SJC", contagem_turnos, inactive_re=inactive_re, historico_turnos=historico_turnos)
            if t1_sjc:
                contagem_turnos[t1_sjc['re']] = contagem_turnos.get(t1_sjc['re'], 0) + 1
                cursor.execute(
                    "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                    (data_str, "SJC", "08:00 às 17:00", t1_sjc['re'], t1_sjc['nome'])
                )

                t2_sjc = obter_proximo_tecnico("SJC", contagem_turnos, tecnico_excluir=t1_sjc['re'], inactive_re=inactive_re, historico_turnos=historico_turnos)
                if t2_sjc:
                    contagem_turnos[t2_sjc['re']] = contagem_turnos.get(t2_sjc['re'], 0) + 1
                    cursor.execute(
                        "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                        (data_str, "SJC", "17:00 às 06:00", t2_sjc['re'], t2_sjc['nome'])
                    )

            # TAUBATÉ
            t1_taub = obter_proximo_tecnico("TAUBATE", contagem_turnos, inactive_re=inactive_re, historico_turnos=historico_turnos)
            if t1_taub:
                contagem_turnos[t1_taub['re']] = contagem_turnos.get(t1_taub['re'], 0) + 1
                cursor.execute(
                    "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                    (data_str, "TAUBATE", "08:00 às 17:00", t1_taub['re'], t1_taub['nome'])
                )

                t2_taub = obter_proximo_tecnico("TAUBATE", contagem_turnos, tecnico_excluir=t1_taub['re'], inactive_re=inactive_re, historico_turnos=historico_turnos)
                if t2_taub:
                    contagem_turnos[t2_taub['re']] = contagem_turnos.get(t2_taub['re'], 0) + 1
                    cursor.execute(
                        "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                        (data_str, "TAUBATE", "17:00 às 06:00", t2_taub['re'], t2_taub['nome'])
                    )

            # LITORAL
            t_lit = obter_proximo_tecnico("LITORAL", contagem_turnos, inactive_re=inactive_re, historico_turnos=historico_turnos)
            if t_lit:
                contagem_turnos[t_lit['re']] = contagem_turnos.get(t_lit['re'], 0) + 1
                cursor.execute(
                    "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                    (data_str, "LITORAL", "08:00 às 17:00", t_lit['re'], t_lit['nome'])
                )

    conn.commit()
    cursor.close()
    conn.close()

@app.route('/')
def dashboard():
    mes_selecionado = resolve_dashboard_month()

    def proximo_mes(data):
        if data.month == 12:
            return data.replace(year=data.year + 1, month=1)
        return data.replace(month=data.month + 1)

    def mes_anterior(data):
        if data.month == 1:
            return data.replace(year=data.year - 1, month=12)
        return data.replace(month=data.month - 1)

    prev_month = mes_anterior(mes_selecionado)
    next_month = proximo_mes(mes_selecionado)
    proximo_sabado, proximo_domingo = resolve_dashboard_weekend_dates(mes_selecionado)

    conn = get_db_connection()
    cursor = conn.cursor()

    primeiro_dia = f"{mes_selecionado.year}-{mes_selecionado.month:02d}-01"
    ultimo_dia = f"{mes_selecionado.year}-{mes_selecionado.month:02d}-{monthrange(mes_selecionado.year, mes_selecionado.month)[1]}"
    cursor.execute(
        "SELECT id, to_char(data, 'DD/MM/YYYY') as data_formatada, area, turno, tecnico_re, tecnico_nome "
        "FROM escala WHERE data BETWEEN %s AND %s ORDER BY data ASC, area ASC, turno ASC",
        (primeiro_dia, ultimo_dia)
    )
    escala_mensal = cursor.fetchall()

    if proximo_sabado and proximo_domingo:
        cursor.execute(
            "SELECT to_char(data, 'DD/MM/YYYY') as data_formatada, area, turno, tecnico_re, tecnico_nome "
            "FROM escala WHERE data IN (%s, %s) ORDER BY data ASC, area ASC, turno ASC",
            (proximo_sabado, proximo_domingo)
        )
        escala_fds = cursor.fetchall()
    else:
        escala_fds = []

    feriados_do_mes = load_holidays_for_year(mes_selecionado.year)
    calendar_days = build_month_calendar_view(mes_selecionado, escala_mensal, holiday_dates=feriados_do_mes)

    cursor.close()
    conn.close()
    return render_template(
        'dashboard.html',
        calendar_days=calendar_days,
        fds=escala_fds,
        mes_ano=mes_selecionado.strftime("%m/%Y"),
        mes_selecionado=mes_selecionado,
        prev_month=prev_month,
        next_month=next_month,
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        passwd = request.form['password']
        if user in ADMIN_USERS and ADMIN_USERS[user] == passwd:
            session['admin'] = user
            return redirect(url_for('admin'))
        flash('Usuário ou senha inválidos!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('dashboard'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'admin' not in session:
        return redirect(url_for('login'))

    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        acao = request.form.get('action')

        if acao == 'gerar':
            mes = int(request.form.get('mes'))
            ano = int(request.form.get('ano'))
            gerar_escala_automatica(ano, mes)
            flash(f'Escala de {mes:02d}/{ano} gerada com sucesso!')

        elif acao == 'editar':
            row_id = request.form.get('id')
            novo_re = request.form.get('tecnico_re')
            nome_mapped = next((t['nome'] for t in TECNICOS if t['re'] == novo_re), "")

            cursor.execute("UPDATE escala SET tecnico_re = %s, tecnico_nome = %s WHERE id = %s", (novo_re, nome_mapped, row_id))
            conn.commit()
            flash('Alteração manual efetuada com sucesso!')

        elif acao == 'add_holiday':
            holiday_date = request.form.get('holiday_date')
            holiday_description = request.form.get('holiday_description', '').strip()

            if not holiday_date:
                flash('Informe a data do feriado manual.')
            else:
                cursor.execute(
                    "INSERT INTO feriados_manuais (data, descricao) VALUES (%s, %s) ON CONFLICT (data) DO UPDATE SET descricao = EXCLUDED.descricao",
                    (holiday_date, holiday_description or 'Feriado manual'),
                )
                conn.commit()
                flash('Feriado manual salvo com sucesso!')

        elif acao == 'add_inatividade':
            selected_tecnicos = request.form.getlist('tecnico_re')
            data_inicio = request.form.get('data_inicio')
            data_fim = request.form.get('data_fim')
            motivo = request.form.get('motivo')

            if not selected_tecnicos or not data_inicio or not data_fim or not motivo:
                flash('Preencha técnico, período e motivo para registrar a inatividade.')
            else:
                for tecnico_re in selected_tecnicos:
                    tecnico = next((t for t in TECNICOS if t['re'] == tecnico_re), None)
                    if not tecnico:
                        continue
                    cursor.execute(
                        "INSERT INTO tecnico_inativo (tecnico_re, tecnico_nome, data_inicio, data_fim, motivo) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tecnico_re, data_inicio, data_fim, motivo) DO NOTHING",
                        (tecnico_re, tecnico['nome'], data_inicio, data_fim, motivo),
                    )
                conn.commit()
                flash('Técnicos marcados como inativos para o período selecionado!')

    cursor.execute("SELECT id, to_char(data, 'DD/MM/YYYY') as data_formatada, area, turno, tecnico_re, tecnico_nome FROM escala ORDER BY data DESC, area ASC, turno ASC")
    escala_total = cursor.fetchall()
    cursor.execute("SELECT to_char(data, 'DD/MM/YYYY') as data_formatada, descricao FROM feriados_manuais ORDER BY data ASC")
    feriados_manuais = cursor.fetchall()
    cursor.execute(
        "SELECT to_char(data_inicio, 'DD/MM/YYYY') as data_inicio_formatada, to_char(data_fim, 'DD/MM/YYYY') as data_fim_formatada, tecnico_re, tecnico_nome, motivo FROM tecnico_inativo ORDER BY data_inicio ASC, tecnico_nome ASC"
    )
    tecnicos_inativos = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('admin.html', escala=escala_total, tecnicos=TECNICOS, feriados_manuais=feriados_manuais, tecnicos_inativos=tecnicos_inativos)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)