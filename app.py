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


def load_holidays_for_year(ano):
    feriados = fetch_public_holidays(ano)
    feriados.update(SP_STATE_HOLIDAYS.get(ano, set()))
    feriados.update(load_school_holidays(ano))
    return feriados


def is_plantao_day(data, feriados=None):
    if feriados is None:
        feriados = load_holidays_for_year(data.year)

    data_str = data.strftime("%Y-%m-%d")
    return data.weekday() >= 5 or data_str in feriados


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
    conn.commit()
    cursor.close()
    conn.close()

def obter_proximo_tecnico(area, contagem_turnos, tecnico_excluir=None):
    """Retorna o técnico com menos turnos na área, excluindo opcionalmente um técnico específico"""
    tecs_area = [t for t in TECNICOS if t['area'] == area]
    
    if tecnico_excluir:
        tecs_area = [t for t in tecs_area if t['re'] != tecnico_excluir]
    
    if not tecs_area:
        tecs_area = [t for t in TECNICOS if t['area'] == area]
    
    tecs_area.sort(key=lambda t: contagem_turnos.get(t['re'], 0))
    return tecs_area[0]

def gerar_escala_automatica(ano, mes):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    primeiro_dia = f"{ano}-{mes:02d}-01"
    ultimo_dia = f"{ano}-{mes:02d}-{monthrange(ano, mes)[1]}"
    
    cursor.execute("DELETE FROM escala WHERE data BETWEEN %s AND %s", (primeiro_dia, ultimo_dia))
    
    cursor.execute("SELECT tecnico_re, COUNT(*) FROM escala GROUP BY tecnico_re")
    contagem_turnos = dict(cursor.fetchall())
    
    num_dias = monthrange(ano, mes)[1]
    feriados_do_ano = load_holidays_for_year(ano)

    for dia in range(1, num_dias + 1):
        data_atual = datetime.date(ano, mes, dia)
        data_str = data_atual.strftime("%Y-%m-%d")

        is_plantao = is_plantao_day(data_atual, feriados_do_ano)

        if is_plantao:
            # SJC
            t1_sjc = obter_proximo_tecnico("SJC", contagem_turnos)
            contagem_turnos[t1_sjc['re']] = contagem_turnos.get(t1_sjc['re'], 0) + 1
            cursor.execute(
                "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                (data_str, "SJC", "08:00 às 17:00", t1_sjc['re'], t1_sjc['nome'])
            )
            
            t2_sjc = obter_proximo_tecnico("SJC", contagem_turnos, tecnico_excluir=t1_sjc['re'])
            contagem_turnos[t2_sjc['re']] = contagem_turnos.get(t2_sjc['re'], 0) + 1
            cursor.execute(
                "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                (data_str, "SJC", "17:00 às 06:00", t2_sjc['re'], t2_sjc['nome'])
            )

            # TAUBATÉ
            t1_taub = obter_proximo_tecnico("TAUBATE", contagem_turnos)
            contagem_turnos[t1_taub['re']] = contagem_turnos.get(t1_taub['re'], 0) + 1
            cursor.execute(
                "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                (data_str, "TAUBATE", "08:00 às 17:00", t1_taub['re'], t1_taub['nome'])
            )
            
            t2_taub = obter_proximo_tecnico("TAUBATE", contagem_turnos, tecnico_excluir=t1_taub['re'])
            contagem_turnos[t2_taub['re']] = contagem_turnos.get(t2_taub['re'], 0) + 1
            cursor.execute(
                "INSERT INTO escala (data, area, turno, tecnico_re, tecnico_nome) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (data, area, turno) DO UPDATE SET tecnico_re = EXCLUDED.tecnico_re, tecnico_nome = EXCLUDED.tecnico_nome",
                (data_str, "TAUBATE", "17:00 às 06:00", t2_taub['re'], t2_taub['nome'])
            )

            # LITORAL
            t_lit = obter_proximo_tecnico("LITORAL", contagem_turnos)
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
    hoje = datetime.date.today()

    dias_para_sabado = (5 - hoje.weekday()) % 7
    proximo_sabado = hoje + datetime.timedelta(days=dias_para_sabado)
    proximo_domingo = proximo_sabado + datetime.timedelta(days=1)

    conn = get_db_connection()
    cursor = conn.cursor()
    
    primeiro_dia = f"{hoje.year}-{hoje.month:02d}-01"
    ultimo_dia = f"{hoje.year}-{hoje.month:02d}-{monthrange(hoje.year, hoje.month)[1]}"
    cursor.execute(
        "SELECT id, to_char(data, 'DD/MM/YYYY') as data_formatada, area, turno, tecnico_re, tecnico_nome "
        "FROM escala WHERE data BETWEEN %s AND %s ORDER BY data ASC, area ASC, turno ASC", 
        (primeiro_dia, ultimo_dia)
    )
    escala_mensal = cursor.fetchall()
    
    cursor.execute(
        "SELECT to_char(data, 'DD/MM/YYYY') as data_formatada, area, turno, tecnico_re, tecnico_nome "
        "FROM escala WHERE data IN (%s, %s) ORDER BY data ASC, area ASC, turno ASC", 
        (proximo_sabado, proximo_domingo)
    )
    escala_fds = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('dashboard.html', mensal=escala_mensal, fds=escala_fds, mes_ano=hoje.strftime("%m/%Y"))

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
            
    cursor.execute("SELECT id, to_char(data, 'DD/MM/YYYY') as data_formatada, area, turno, tecnico_re, tecnico_nome FROM escala ORDER BY data DESC, area ASC, turno ASC")
    escala_total = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('admin.html', escala=escala_total, tecnicos=TECNICOS)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)