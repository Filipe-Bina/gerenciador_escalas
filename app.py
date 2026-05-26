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
app.secret_key = os.environ.get("SECRET_KEY", "senha-super-secreta")

# =========================================================
# LOGS
# =========================================================

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# =========================================================
# DATABASE
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1,
    )

# =========================================================
# API FERIADOS
# =========================================================

FERIADOS_API_URL = "https://brasilapi.com.br/api/feriados/v1/{ano}"

# =========================================================
# CONEXÃO DB
# =========================================================


def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

# =========================================================
# INIT DB
# =========================================================

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            admin BOOLEAN DEFAULT FALSE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS feriados_manuais (
            id SERIAL PRIMARY KEY,
            data DATE NOT NULL,
            descricao VARCHAR(255)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fds (
            id SERIAL PRIMARY KEY,
            tecnico VARCHAR(255),
            data DATE,
            turno VARCHAR(50)
        )
        """
    )

    cursor.execute(
        "SELECT * FROM usuarios WHERE username = %s",
        ("admin",),
    )
    admin = cursor.fetchone()

    if not admin:
        cursor.execute(
            """
            INSERT INTO usuarios (username, password, admin)
            VALUES (%s, %s, %s)
            """,
            ("admin", "admin123", True),
        )

    cursor.close()
    conn.close()

    app.logger.info("Banco inicializado com sucesso")

# =========================================================
# EXECUTA INIT DB NO STARTUP
# =========================================================

init_db()

# =========================================================
# FERIADOS API
# =========================================================


def fetch_public_holidays(ano):
    try:
        url = FERIADOS_API_URL.format(ano=ano)

        req = urllib_request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        with urllib_request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        return {
            item["date"]
            for item in data
        }

    except Exception as e:
        app.logger.error(f"Erro API feriados: {e}")
        return set()

# =========================================================
# FERIADOS MANUAIS
# =========================================================


def load_manual_holidays_for_year(ano):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            SELECT data
            FROM feriados_manuais
            WHERE EXTRACT(YEAR FROM data) = %s
            """,
            (ano,),
        )
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            row["data"].strftime("%Y-%m-%d")
            for row in rows
        }

    except Exception as e:
        app.logger.error(f"Erro feriados manuais: {e}")
        return set()

# =========================================================
# TODOS FERIADOS
# =========================================================


def load_holidays_for_year(ano):
    api_holidays = fetch_public_holidays(ano)
    manual_holidays = load_manual_holidays_for_year(ano)
    return api_holidays.union(manual_holidays)

# =========================================================
# LOGIN REQUIRED
# =========================================================


def is_logged_in():
    return session.get("logged_in")

# =========================================================
# LOGIN
# =========================================================


@app.route("/login", methods=["GET", "POST"])
def login():
    try:
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT *
                FROM usuarios
                WHERE username = %s
                AND password = %s
                """,
                (username, password),
            )

            user = cursor.fetchone()

            cursor.close()
            conn.close()

            if user:
                session["logged_in"] = True
                session["username"] = user["username"]
                session["admin"] = user["admin"]

                return redirect(url_for("dashboard"))

            flash("Usuário ou senha inválidos")
        return render_template("login.html")

    except Exception as e:
        app.logger.error(f"Erro login: {e}")
        return str(e), 500

# =========================================================
# LOGOUT
# =========================================================


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():
    try:
        if not is_logged_in():
            return redirect(url_for("login"))

        hoje = date.today()

        mes = request.args.get("mes", hoje.month, type=int)
        ano = request.args.get("ano", hoje.year, type=int)

        current_month = date(ano, mes, 1)

        if mes == 1:
            previous_month = date(ano - 1, 12, 1)
        else:
            previous_month = date(ano, mes - 1, 1)

        if mes == 12:
            next_month = date(ano + 1, 1, 1)
        else:
            next_month = date(ano, mes + 1, 1)

        holidays = load_holidays_for_year(ano)

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            SELECT *
            FROM fds
            WHERE EXTRACT(MONTH FROM data) = %s
            AND EXTRACT(YEAR FROM data) = %s
            ORDER BY data ASC
            """,
            (mes, ano),
        )

        fds = cursor.fetchall()

        cursor.close()
        conn.close()

        calendar_weeks = []

        start_day = current_month
        while start_day.weekday() != 0:
            start_day -= timedelta(days=1)

        current_day = start_day

        for _ in range(6):
            week = []

            for _ in range(7):
                date_str = current_day.strftime("%Y-%m-%d")

                entries = [
                    item
                    for item in fds
                    if item["data"].strftime("%Y-%m-%d") == date_str
                ]

                cell = {
                    "date": current_day,
                    "day": current_day.day,
                    "is_current_month": current_day.month == mes,
                    "is_weekend": current_day.weekday() >= 5,
                    "is_holiday": date_str in holidays,
                    "entries": entries,
                }
                week.append(cell)
                current_day += timedelta(days=1)

            calendar_weeks.append(week)

        mes_ano = current_month.strftime("%B/%Y")

        return render_template(
            "dashboard.html",
            fds=fds,
            mes_ano=mes_ano,
            prev_month=previous_month,
            next_month=next_month,
            calendar_weeks=calendar_weeks,
        )

    except Exception as e:
        app.logger.error(f"Erro dashboard: {e}")
        return f"ERRO DASHBOARD: {str(e)}", 500

# =========================================================
# ADMIN
# =========================================================


@app.route("/admin", methods=["GET", "POST"])
def admin():
    try:
        if not is_logged_in():
            return redirect(url_for("login"))

        if not session.get("admin"):
            return redirect(url_for("dashboard"))

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            tecnico = request.form.get("tecnico")
            data = request.form.get("data")
            turno = request.form.get("turno")

            cursor.execute(
                """
                INSERT INTO fds (tecnico, data, turno)
                VALUES (%s, %s, %s)
                """,
                (tecnico, data, turno),
            )

            flash("Registro criado com sucesso")

        cursor.execute(
            """
            SELECT *
            FROM fds
            ORDER BY data DESC
            """
        )

        registros = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            "admin.html",
            registros=registros,
        )

    except Exception as e:
        app.logger.error(f"Erro admin: {e}")
        return f"ERRO ADMIN: {str(e)}", 500

# =========================================================
# HEALTHCHECK
# =========================================================


@app.route("/health")
def health():
    return {
        "status": "ok"
    }

# =========================================================
# START LOCAL
# =========================================================


if __name__ == "__main__":
    app.run(debug=True)