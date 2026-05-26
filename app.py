import os
import json
import logging
from datetime import datetime, timedelta, date
from urllib import request as urllib_request

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

# =========================================================
# CONFIGURAÇÃO APP
# =========================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "senha-super-secreta-gtd-2026")

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# =========================================================
# DATABASE
# =========================================================
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

FERIADOS_API_URL = "https://brasilapi.com.br/api/feriados/v1/{ano}"

# Feriados estaduais SP fixos (mês, dia)
FERIADOS_SP = [
    (1, 25),   # Aniversário de SP
    (7, 9),    # Revolução Constitucionalista
]

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

# =========================================================
# INIT DB — cria todas as tabelas e dados iniciais
# =========================================================
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            admin BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tecnicos (
            id SERIAL PRIMARY KEY,
            re VARCHAR(20) UNIQUE NOT NULL,
            nome VARCHAR(100) NOT NULL,
            area VARCHAR(50) NOT NULL,
            ativo BOOLEAN DEFAULT TRUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inatividades (
            id SERIAL PRIMARY KEY,
            tecnico_id INTEGER REFERENCES tecnicos(id) ON DELETE CASCADE,
            data_inicio DATE NOT NULL,
            data_fim DATE NOT NULL,
            motivo VARCHAR(50) NOT NULL,
            observacao TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feriados_manuais (
            id SERIAL PRIMARY KEY,
            data DATE NOT NULL UNIQUE,
            descricao VARCHAR(255)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fds (
            id SERIAL PRIMARY KEY,
            tecnico_id INTEGER REFERENCES tecnicos(id) ON DELETE CASCADE,
            data DATE NOT NULL,
            area VARCHAR(50) NOT NULL,
            turno VARCHAR(80) NOT NULL,
            UNIQUE(data, area, turno)
        )
    """)

    # Índices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fds_data ON fds(data)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fds_area ON fds(area)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_inatividades_periodo ON inatividades(data_inicio, data_fim)")

    # Admin padrão
    cur.execute("SELECT id FROM usuarios WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO usuarios (username, password, admin) VALUES (%s, %s, %s)",
            ("admin", "admin123", True)
        )

    # Técnicos
    tecnicos_data = [
        # TAUBATÉ (TTE + GUARÁ)
        ("30981", "ANDERSON PEDRO DE SOUZA", "TAUBATE"),
        ("32965", "FÁBIO APARECIDO ALVES", "TAUBATE"),
        ("34322", "JARY OLIVEIRA", "TAUBATE"),
        ("34020", "JOSÉ DIVINO LEOPOLDINO", "TAUBATE"),
        ("30116", "LUIZ RICARDO ALKIMIN", "TAUBATE"),
        ("34892", "RONALDO CAMPOS LEOPOLDO", "TAUBATE"),
        ("30498", "GUIDO FERREIRA SOBRINHO", "TAUBATE"),
        ("30602", "JOSÉ LUIZ RAIMUNDO", "TAUBATE"),
        ("30626", "JOSIMAR PAULO DE AZEVEDO", "TAUBATE"),
        # SJC
        ("33167", "SÉRGIO HENRIQUE DA SILVA", "SJC"),
        ("34298", "VANDERLEI DOS SANTOS", "SJC"),
        ("35383", "ANDERSON MOREIRA", "SJC"),
        ("31369", "SANTIAGO GUIZALBERTI", "SJC"),
        ("30641", "LEIF ERICKSON", "SJC"),
        ("35273", "RODRIGO SILVA", "SJC"),
        ("35476", "JULIARD TEIXEIRA BARBOSA", "SJC"),
        ("32989", "SILVIO TEIXEIRA DE PAIVA", "SJC"),
        # LITORAL
        ("34854", "LUCINEI CAMPOS", "LITORAL"),
        ("32626", "WANDERLEI RODRIGUES SOUZA", "LITORAL"),
        ("30930", "WILTON DIAS FERNANDES", "LITORAL"),
        ("32590", "RENILSON SANTANA DE OLIVEIRA", "LITORAL"),
        ("35384", "JEFERSON ANTUNES", "LITORAL"),
    ]

    for re, nome, area in tecnicos_data:
        cur.execute(
            "INSERT INTO tecnicos (re, nome, area) VALUES (%s, %s, %s) ON CONFLICT (re) DO NOTHING",
            (re, nome, area)
        )

    cur.close()
    conn.close()
    app.logger.info("Banco inicializado com sucesso")

init_db()

# =========================================================
# FERIADOS
# =========================================================
def fetch_public_holidays(ano):
    try:
        url = FERIADOS_API_URL.format(ano=ano)
        req = urllib_request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib_request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return {item["date"] for item in data}
    except Exception as e:
        app.logger.error(f"Erro API feriados: {e}")
        return set()

def load_all_holidays(ano):
    api = fetch_public_holidays(ano)
    # Adiciona feriados estaduais SP
    for mes, dia in FERIADOS_SP:
        try:
            api.add(date(ano, mes, dia).strftime("%Y-%m-%d"))
        except Exception:
            pass
    # Feriados manuais do banco
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT data FROM feriados_manuais WHERE EXTRACT(YEAR FROM data) = %s", (ano,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        for row in rows:
            api.add(row["data"].strftime("%Y-%m-%d"))
    except Exception as e:
        app.logger.error(f"Erro feriados manuais: {e}")
    return api

# =========================================================
# HELPERS
# =========================================================
def is_logged_in():
    return session.get("logged_in", False)

def is_admin():
    return session.get("admin", False)

def get_tecnicos_ativos():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM tecnicos WHERE ativo = TRUE ORDER BY area, nome")
    result = cur.fetchall()
    cur.close()
    conn.close()
    return result

def get_inativos_no_periodo(data_inicio, data_fim):
    """Retorna set de tecnico_id que têm inatividade sobrepondo o período."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT DISTINCT tecnico_id FROM inatividades
        WHERE data_inicio <= %s AND data_fim >= %s
    """, (data_fim, data_inicio))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {r["tecnico_id"] for r in rows}

# =========================================================
# ALGORITMO DE GERAÇÃO DE ESCALA
# =========================================================
def gerar_escala_mes(mes, ano):
    """
    Gera escala automática para o mês/ano.
    Regras:
    - SJC: 2 técnicos por dia (08-17 e 17-06)
    - TAUBATE: 2 técnicos por dia (08-17 e 17-06)
    - LITORAL: 1 técnico por dia (08-17)
    - Apenas sábados, domingos e feriados
    - Distribuição justa (quem trabalhou menos vai primeiro)
    - Técnicos inativos são excluídos
    - Ninguém trabalha dois dias seguidos no mesmo turno
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Remove escala existente do mês
    cur.execute("""
        DELETE FROM fds
        WHERE EXTRACT(MONTH FROM data) = %s AND EXTRACT(YEAR FROM data) = %s
    """, (mes, ano))

    holidays = load_all_holidays(ano)

    # Dias que entram na escala (sáb, dom, feriados no mês)
    dias_escala = []
    d = date(ano, mes, 1)
    while d.month == mes:
        d_str = d.strftime("%Y-%m-%d")
        if d.weekday() >= 5 or d_str in holidays:
            dias_escala.append(d)
        d += timedelta(days=1)

    # Carrega técnicos por área
    cur.execute("SELECT * FROM tecnicos WHERE ativo = TRUE ORDER BY area, nome")
    all_tecnicos = cur.fetchall()

    tecnicos_por_area = {}
    for t in all_tecnicos:
        tecnicos_por_area.setdefault(t["area"], []).append(t)

    # Conta quantas vezes cada técnico já trabalhou no ano (para equilíbrio)
    cur.execute("""
        SELECT t.id, COUNT(f.id) as total
        FROM tecnicos t
        LEFT JOIN fds f ON f.tecnico_id = t.id
            AND EXTRACT(YEAR FROM f.data) = %s
        GROUP BY t.id
    """, (ano,))
    contagem = {r["id"]: r["total"] for r in cur.fetchall()}

    def sortear_tecnico(tecnicos_disponiveis, usados_recente):
        """Escolhe o técnico com menos plantões, excluindo os usados recentemente."""
        candidatos = [t for t in tecnicos_disponiveis if t["id"] not in usados_recente]
        if not candidatos:
            candidatos = tecnicos_disponiveis  # fallback
        candidatos.sort(key=lambda t: contagem.get(t["id"], 0))
        escolhido = candidatos[0]
        contagem[escolhido["id"]] = contagem.get(escolhido["id"], 0) + 1
        return escolhido

    config_areas = {
        "SJC":     [("08:00 às 17:00", False), ("17:00 às 06:00", False)],
        "TAUBATE": [("08:00 às 17:00", False), ("17:00 às 06:00", False)],
        "LITORAL": [("08:00 às 17:00", True)],  # True = apenas 1 técnico
    }

    # Rastreia últimos técnicos usados por (area, turno) para evitar sequência
    ultimo_por_slot = {}  # (area, turno) -> set de tecnico_id

    for dia in dias_escala:
        inativos = get_inativos_no_periodo(dia, dia)

        for area, turnos in config_areas.items():
            tecnicos_area = [t for t in tecnicos_por_area.get(area, []) if t["id"] not in inativos]
            usados_hoje = set()

            for turno_label, _ in turnos:
                slot_key = (area, turno_label)
                recentes = ultimo_por_slot.get(slot_key, set())
                disponiveis = [t for t in tecnicos_area if t["id"] not in usados_hoje]

                if not disponiveis:
                    disponiveis = tecnicos_area  # fallback de emergência

                tecnico = sortear_tecnico(disponiveis, recentes)
                usados_hoje.add(tecnico["id"])
                ultimo_por_slot[slot_key] = {tecnico["id"]}

                try:
                    cur.execute("""
                        INSERT INTO fds (tecnico_id, data, area, turno)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (data, area, turno) DO NOTHING
                    """, (tecnico["id"], dia, area, turno_label))
                except Exception as e:
                    app.logger.error(f"Erro inserindo escala {dia} {area} {turno_label}: {e}")

    cur.close()
    conn.close()
    app.logger.info(f"Escala gerada: {mes}/{ano}")
    return len(dias_escala)

# =========================================================
# ROTAS — LOGIN / LOGOUT
# =========================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        passwd = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Busca o usuário direto na nova tabela 'usuarios' do seu Schema v2.0
        cursor.execute("SELECT id, username, admin FROM usuarios WHERE username = %s AND password = %s", (user, passwd))
        usuario_valido = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if usuario_valido:
            # 2. Grava explicitamente os dados de controle na sessão do Flask
            session['admin'] = usuario_valido['username']
            session['is_admin'] = usuario_valido['admin']
            
            # 3. Força o redirecionamento imediato para a área administrativa
            return redirect(url_for('admin'))
            
        flash('Usuário ou senha inválidos!')
    return render_template('login.html')


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("login"))


# =========================================================
# ROTA — DASHBOARD PÚBLICO (técnicos visualizam)
# =========================================================
@app.route("/")
def dashboard():
    try:
        hoje = date.today()
        mes = request.args.get("mes", hoje.month, type=int)
        ano = request.args.get("ano", hoje.year, type=int)

        # Valida mês/ano
        if not (1 <= mes <= 12):
            mes = hoje.month
        if not (2020 <= ano <= 2030):
            ano = hoje.year

        current_month = date(ano, mes, 1)
        prev_month = date(ano - 1, 12, 1) if mes == 1 else date(ano, mes - 1, 1)
        next_month = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)

        holidays = load_all_holidays(ano)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT f.id, f.data, f.area, f.turno,
                   t.nome as tecnico_nome, t.re as tecnico_re
            FROM fds f
            JOIN tecnicos t ON t.id = f.tecnico_id
            WHERE EXTRACT(MONTH FROM f.data) = %s
              AND EXTRACT(YEAR FROM f.data) = %s
            ORDER BY f.data, f.area, f.turno
        """, (mes, ano))
        fds = cur.fetchall()

        cur.close()
        conn.close()

        # Próximo FDS
        proximo_fds = None
        for d in range(0, 14):
            check = hoje + timedelta(days=d)
            if check.weekday() >= 5 or check.strftime("%Y-%m-%d") in holidays:
                proximo_fds = check
                break

        proximo_fds_entries = []
        if proximo_fds:
            proximo_fds_entries = [
                f for f in fds
                if f["data"] == proximo_fds
            ]
            # Se não está no mês atual, buscar no banco
            if not proximo_fds_entries and proximo_fds.month != mes:
                conn2 = get_db_connection()
                cur2 = conn2.cursor(cursor_factory=RealDictCursor)
                cur2.execute("""
                    SELECT f.id, f.data, f.area, f.turno,
                           t.nome as tecnico_nome, t.re as tecnico_re
                    FROM fds f
                    JOIN tecnicos t ON t.id = f.tecnico_id
                    WHERE f.data = %s
                    ORDER BY f.area, f.turno
                """, (proximo_fds,))
                proximo_fds_entries = cur2.fetchall()
                cur2.close()
                conn2.close()

        # Monta calendário
        calendar_weeks = []
        start_day = current_month
        while start_day.weekday() != 0:
            start_day -= timedelta(days=1)

        current_day = start_day
        for _ in range(6):
            week = []
            for _ in range(7):
                d_str = current_day.strftime("%Y-%m-%d")
                entries = [f for f in fds if f["data"].strftime("%Y-%m-%d") == d_str]
                week.append({
                    "date": current_day,
                    "day": current_day.day,
                    "is_current_month": current_day.month == mes,
                    "is_weekend": current_day.weekday() >= 5,
                    "is_holiday": d_str in holidays,
                    "entries": entries,
                })
                current_day += timedelta(days=1)
            calendar_weeks.append(week)

        MESES_PT = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }
        mes_nome = f"{MESES_PT[mes]}/{ano}"

        return render_template(
            "dashboard.html",
            fds=fds,
            mes_ano=mes_nome,
            prev_month=prev_month,
            next_month=next_month,
            calendar_weeks=calendar_weeks,
            proximo_fds=proximo_fds,
            proximo_fds_entries=proximo_fds_entries,
            is_admin=is_admin(),
            is_logged_in=is_logged_in(),
        )
    except Exception as e:
        app.logger.error(f"Erro dashboard: {e}")
        return f"ERRO: {e}", 500


# =========================================================
# ROTA — PAINEL ADMIN
# =========================================================
@app.route("/admin", methods=["GET", "POST"])
def admin():
    # Se a sessão não encontrar a chave 'admin', joga para a tela de login
    if 'admin' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":
        action = request.form.get("action", "")

        # --- GERAR ESCALA AUTOMÁTICA ---
        if action == "gerar":
            mes = int(request.form.get("mes", 6))
            ano = int(request.form.get("ano", 2026))
            try:
                qtd = gerar_escala_mes(mes, ano)
                flash(f"Escala gerada com sucesso! {qtd} dias de plantão escalados.", "success")
            except Exception as e:
                flash(f"Erro ao gerar escala: {e}", "danger")
                app.logger.error(f"Erro gerar escala: {e}")

        # --- ADICIONAR FERIADO MANUAL ---
        elif action == "add_holiday":
            holiday_date = request.form.get("holiday_date")
            holiday_desc = request.form.get("holiday_description", "")
            try:
                cur.execute(
                    "INSERT INTO feriados_manuais (data, descricao) VALUES (%s, %s) ON CONFLICT (data) DO UPDATE SET descricao = EXCLUDED.descricao",
                    (holiday_date, holiday_desc)
                )
                flash("Feriado salvo com sucesso!", "success")
            except Exception as e:
                flash(f"Erro ao salvar feriado: {e}", "danger")

        # --- MARCAR INATIVIDADE ---
        elif action == "add_inatividade":
            tecnico_res = request.form.getlist("tecnico_re")
            data_inicio = request.form.get("data_inicio")
            data_fim = request.form.get("data_fim")
            motivo = request.form.get("motivo")
            observacao = request.form.get("observacao", "")
            try:
                for re in tecnico_res:
                    cur.execute("SELECT id FROM tecnicos WHERE re = %s", (re,))
                    tec = cur.fetchone()
                    if tec:
                        cur.execute("""
                            INSERT INTO inatividades (tecnico_id, data_inicio, data_fim, motivo, observacao)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (tec["id"], data_inicio, data_fim, motivo, observacao))
                flash("Inatividade registrada com sucesso!", "success")
            except Exception as e:
                flash(f"Erro ao registrar inatividade: {e}", "danger")

        # --- REMOVER INATIVIDADE ---
        elif action == "del_inatividade":
            inatividade_id = request.form.get("inatividade_id")
            try:
                cur.execute("DELETE FROM inatividades WHERE id = %s", (inatividade_id,))
                flash("Inatividade removida.", "success")
            except Exception as e:
                flash(f"Erro: {e}", "danger")

        # --- REMOVER FERIADO ---
        elif action == "del_feriado":
            feriado_id = request.form.get("feriado_id")
            try:
                cur.execute("DELETE FROM feriados_manuais WHERE id = %s", (feriado_id,))
                flash("Feriado removido.", "success")
            except Exception as e:
                flash(f"Erro: {e}", "danger")

        # --- EDITAR REGISTRO DE ESCALA (TROCA MANUAL) ---
        elif action == "editar":
            fds_id = request.form.get("id")
            tecnico_re = request.form.get("tecnico_re")
            try:
                cur.execute("SELECT id FROM tecnicos WHERE re = %s", (tecnico_re,))
                tec = cur.fetchone()
                if tec:
                    cur.execute("UPDATE fds SET tecnico_id = %s WHERE id = %s", (tec["id"], fds_id))
                    flash("Escala atualizada com sucesso!", "success")
                else:
                    flash("Técnico não encontrado.", "danger")
            except Exception as e:
                flash(f"Erro ao editar: {e}", "danger")

        return redirect(url_for("admin_panel"))

    # GET — Carrega dados para o painel
    hoje = date.today()
    mes = request.args.get("mes", hoje.month, type=int)
    ano = request.args.get("ano", hoje.year, type=int)

    # Tecnicos
    cur.execute("SELECT * FROM tecnicos WHERE ativo = TRUE ORDER BY area, nome")
    tecnicos = cur.fetchall()

    # Feriados manuais
    cur.execute("SELECT * FROM feriados_manuais ORDER BY data")
    feriados_raw = cur.fetchall()
    feriados_manuais = []
    for f in feriados_raw:
        feriados_manuais.append({
            **f,
            "data_formatada": f["data"].strftime("%d/%m/%Y")
        })

    # Inatividades
    cur.execute("""
        SELECT i.id, i.data_inicio, i.data_fim, i.motivo, i.observacao,
               t.nome as tecnico_nome, t.re as tecnico_re, t.area as tecnico_area
        FROM inatividades i
        JOIN tecnicos t ON t.id = i.tecnico_id
        ORDER BY i.data_inicio DESC
    """)
    inat_raw = cur.fetchall()
    tecnicos_inativos = []
    for i in inat_raw:
        tecnicos_inativos.append({
            **i,
            "data_inicio_formatada": i["data_inicio"].strftime("%d/%m/%Y"),
            "data_fim_formatada": i["data_fim"].strftime("%d/%m/%Y"),
        })

    # Escala do mês selecionado
    cur.execute("""
        SELECT f.id, f.data, f.area, f.turno,
               t.nome as tecnico_nome, t.re as tecnico_re
        FROM fds f
        JOIN tecnicos t ON t.id = f.tecnico_id
        WHERE EXTRACT(MONTH FROM f.data) = %s
          AND EXTRACT(YEAR FROM f.data) = %s
        ORDER BY f.data, f.area, f.turno
    """, (mes, ano))
    escala_raw = cur.fetchall()
    escala = []
    DIAS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    for r in escala_raw:
        escala.append({
            **r,
            "data_formatada": f"{DIAS_PT[r['data'].weekday()]} {r['data'].strftime('%d/%m/%Y')}",
        })

    cur.close()
    conn.close()

    MESES_PT = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    prev_month = date(ano - 1, 12, 1) if mes == 1 else date(ano, mes - 1, 1)
    next_month = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)

    return render_template(
        "admin.html",
        tecnicos=tecnicos,
        feriados_manuais=feriados_manuais,
        tecnicos_inativos=tecnicos_inativos,
        escala=escala,
        mes=mes,
        ano=ano,
        mes_nome=MESES_PT.get(mes, ""),
        prev_month=prev_month,
        next_month=next_month,
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True)
