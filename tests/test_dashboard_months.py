"""Dashboard público e navegação entre meses (CT-DSH)."""
from datetime import date

import pytest


def test_ct_dsh_01_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_ct_dsh_02_dashboard_publico_carrega_sem_login(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_ct_dsh_03_mes_informado_aparece_no_titulo(client):
    resp = client.get("/?mes=3&ano=2026")
    assert resp.status_code == 200
    assert "Março/2026".encode() in resp.data


@pytest.mark.parametrize("mes", [0, 13, -1, 99])
def test_ct_dsh_04_mes_invalido_volta_para_mes_atual(client, mes):
    hoje = date.today()
    resp = client.get(f"/?mes={mes}&ano={hoje.year}")
    assert resp.status_code == 200
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
             "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    assert f"{meses[hoje.month - 1]}/{hoje.year}".encode() in resp.data


def test_ct_dsh_05_parametro_nao_numerico_nao_quebra(client):
    resp = client.get("/?mes=abc&ano=xyz")
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "mes,ano,anterior,proximo",
    [
        (1, 2026, "mes=12&ano=2025", "mes=2&ano=2026"),
        (12, 2026, "mes=11&ano=2026", "mes=1&ano=2027"),
        (6, 2026, "mes=5&ano=2026", "mes=7&ano=2026"),
    ],
    ids=["virada-jan", "virada-dez", "meio-do-ano"],
)
def test_ct_dsh_06_navegacao_mes_anterior_e_proximo(client, mes, ano, anterior, proximo):
    html = client.get(f"/?mes={mes}&ano={ano}").get_data(as_text=True)
    assert anterior in html
    assert proximo in html


def test_ct_dsh_07_escala_gerada_aparece_no_dashboard(client, escala_marco_2026):
    html = client.get("/?mes=3&ano=2026").get_data(as_text=True)
    assert "08:00 às 17:00" in html
    assert "17:00 às 06:00" in html


def test_ct_dsh_08_dashboard_aceita_anos_futuros(client):
    """Regressão do BUG-003 (corrigido): antes, qualquer ano depois de 2030 era ignorado."""
    ano = date.today().year + 5
    resp = client.get(f"/?mes=1&ano={ano}")
    assert f"Janeiro/{ano}".encode() in resp.data


@pytest.mark.parametrize("ano", [1900, 9999, -1])
def test_ct_dsh_09_ano_absurdo_volta_para_o_ano_atual(client, ano):
    hoje = date.today()
    resp = client.get(f"/?mes=1&ano={ano}")
    assert resp.status_code == 200
    assert f"Janeiro/{hoje.year}".encode() in resp.data


def test_ct_dsh_10_aviso_de_acesso_restrito_aparece_no_dashboard(client, usuario_comum):
    client.post("/login", data=usuario_comum)
    resp = client.get("/admin", follow_redirects=True)
    assert "Acesso restrito a administradores".encode() in resp.data
