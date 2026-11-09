"""
Fixtures compartilhadas da suíte de testes do Gerenciador de Escalas.

Os testes rodam contra um PostgreSQL real (o mesmo banco usado em produção),
apontado pela variável DATABASE_URL. Localmente:

    export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/escalas_test
    pytest

No GitHub Actions o banco sobe como "service container" (ver .github/workflows/tests.yml).

A API externa de feriados (BrasilAPI) é substituída por um conjunto fixo,
para que os testes sejam determinísticos e não dependam de rede.
"""
import os
import sys
from datetime import date

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/escalas_test"
)
os.environ.setdefault("SECRET_KEY", "chave-de-teste")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module  # noqa: E402  (init_db() roda no import)

# Feriados nacionais "fixos" usados nos testes (formato da BrasilAPI: YYYY-MM-DD)
FERIADOS_FAKE = {
    2026: {
        "2026-01-01", "2026-04-03", "2026-04-21", "2026-05-01", "2026-06-04",
        "2026-09-07", "2026-10-12", "2026-11-02", "2026-11-15", "2026-11-20",
        "2026-12-25",
    },
    2027: {"2027-01-01", "2027-12-25"},
}


@pytest.fixture(autouse=True)
def feriados_sem_rede(monkeypatch):
    """Nenhum teste chama a internet: a API de feriados devolve um conjunto fixo."""
    monkeypatch.setattr(
        app_module,
        "fetch_public_holidays",
        lambda ano: set(FERIADOS_FAKE.get(ano, set())),
    )


@pytest.fixture(autouse=True)
def banco_limpo():
    """Cada teste começa com escala, inatividades e feriados manuais vazios."""
    conn = app_module.get_db_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE fds, inatividades, feriados_manuais RESTART IDENTITY")
    cur.execute("UPDATE tecnicos SET ativo = TRUE")
    cur.execute("DELETE FROM usuarios WHERE username <> 'admin'")
    cur.close()
    conn.close()
    yield


@pytest.fixture
def app():
    app_module.app.config.update(TESTING=True)
    return app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(client):
    """Cliente já autenticado com o usuário administrador padrão."""
    resp = client.post("/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 302
    return client


@pytest.fixture
def usuario_comum():
    """Cria um usuário SEM permissão de administrador."""
    conn = app_module.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO usuarios (username, password, admin) VALUES (%s, %s, %s)",
        ("tecnico", "tecnico123", False),
    )
    cur.close()
    conn.close()
    return {"username": "tecnico", "password": "tecnico123"}


@pytest.fixture
def db():
    """Executa SQL de apoio e devolve linhas como dicionários."""
    from psycopg2.extras import RealDictCursor

    def query(sql, params=None):
        conn = app_module.get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else None
        cur.close()
        conn.close()
        return rows

    return query


@pytest.fixture
def escala_marco_2026(db):
    """Gera a escala de março/2026 e devolve os registros gravados."""
    app_module.gerar_escala_mes(3, 2026)
    return db(
        "SELECT f.data, f.area, f.turno, f.tecnico_id, t.area AS area_tecnico "
        "FROM fds f JOIN tecnicos t ON t.id = f.tecnico_id ORDER BY f.data, f.area, f.turno"
    )


def fins_de_semana(mes, ano):
    d = date(ano, mes, 1)
    dias = []
    while d.month == mes:
        if d.weekday() >= 5:
            dias.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    return dias
