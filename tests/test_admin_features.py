"""Funcionalidades do painel administrativo (CT-ADM)."""
from datetime import date

import pytest


def test_ct_adm_01_painel_carrega_para_admin(admin_client):
    resp = admin_client.get("/admin")
    assert resp.status_code == 200


def test_ct_adm_02_gerar_escala_pelo_painel(admin_client, db):
    resp = admin_client.post(
        "/admin", data={"action": "gerar", "mes": "3", "ano": "2026"}, follow_redirects=True
    )
    assert "Escala gerada com sucesso".encode() in resp.data
    assert db("SELECT COUNT(*) AS n FROM fds")[0]["n"] > 0


def test_ct_adm_03_cadastrar_feriado_manual(admin_client, db):
    admin_client.post("/admin", data={
        "action": "add_holiday", "holiday_date": "2026-03-19",
        "holiday_description": "Padroeiro",
    })
    feriados = db("SELECT data, descricao FROM feriados_manuais")
    assert feriados == [{"data": date(2026, 3, 19), "descricao": "Padroeiro"}]


def test_ct_adm_04_feriado_repetido_atualiza_descricao(admin_client, db):
    for desc in ("Primeira", "Corrigida"):
        admin_client.post("/admin", data={
            "action": "add_holiday", "holiday_date": "2026-03-19",
            "holiday_description": desc,
        })
    feriados = db("SELECT descricao FROM feriados_manuais")
    assert feriados == [{"descricao": "Corrigida"}]


def test_ct_adm_05_remover_feriado_manual(admin_client, db):
    admin_client.post("/admin", data={"action": "add_holiday", "holiday_date": "2026-03-19"})
    feriado_id = db("SELECT id FROM feriados_manuais")[0]["id"]
    admin_client.post("/admin", data={"action": "del_feriado", "feriado_id": feriado_id})
    assert db("SELECT 1 FROM feriados_manuais") == []


def test_ct_adm_06_registrar_inatividade_para_varios_tecnicos(admin_client, db):
    res = [r["re"] for r in db("SELECT re FROM tecnicos WHERE area = 'SJC' LIMIT 2")]
    admin_client.post("/admin", data={
        "action": "add_inatividade", "tecnico_re": res,
        "data_inicio": "2026-03-01", "data_fim": "2026-03-10", "motivo": "Férias",
    })
    assert db("SELECT COUNT(*) AS n FROM inatividades")[0]["n"] == 2


def test_ct_adm_07_remover_inatividade(admin_client, db):
    re = db("SELECT re FROM tecnicos LIMIT 1")[0]["re"]
    admin_client.post("/admin", data={
        "action": "add_inatividade", "tecnico_re": re,
        "data_inicio": "2026-03-01", "data_fim": "2026-03-10", "motivo": "Férias",
    })
    inat_id = db("SELECT id FROM inatividades")[0]["id"]
    admin_client.post("/admin", data={"action": "del_inatividade", "inatividade_id": inat_id})
    assert db("SELECT 1 FROM inatividades") == []


def test_ct_adm_08_troca_manual_de_tecnico_na_escala(admin_client, db):
    admin_client.post("/admin", data={"action": "gerar", "mes": "3", "ano": "2026"})
    registro = db("SELECT id, tecnico_id FROM fds WHERE area = 'SJC' LIMIT 1")[0]
    outro = db(
        "SELECT id, re FROM tecnicos WHERE area = 'SJC' AND id <> %s LIMIT 1",
        (registro["tecnico_id"],),
    )[0]
    admin_client.post("/admin", data={
        "action": "editar", "id": registro["id"], "tecnico_re": outro["re"],
    })
    atualizado = db("SELECT tecnico_id FROM fds WHERE id = %s", (registro["id"],))[0]
    assert atualizado["tecnico_id"] == outro["id"]


def test_ct_adm_09_troca_com_re_inexistente_mostra_erro(admin_client, db):
    admin_client.post("/admin", data={"action": "gerar", "mes": "3", "ano": "2026"})
    registro = db("SELECT id, tecnico_id FROM fds LIMIT 1")[0]
    resp = admin_client.post(
        "/admin", data={"action": "editar", "id": registro["id"], "tecnico_re": "00000"},
        follow_redirects=True,
    )
    assert "Técnico não encontrado".encode() in resp.data
    assert db("SELECT tecnico_id FROM fds WHERE id = %s", (registro["id"],))[0] == {
        "tecnico_id": registro["tecnico_id"]
    }


@pytest.mark.xfail(
    strict=True,
    reason="BUG-004: inatividade com data final anterior à inicial é aceita sem validação.",
)
def test_ct_adm_10_rejeita_inatividade_com_periodo_invertido(admin_client, db):
    re = db("SELECT re FROM tecnicos LIMIT 1")[0]["re"]
    admin_client.post("/admin", data={
        "action": "add_inatividade", "tecnico_re": re,
        "data_inicio": "2026-03-20", "data_fim": "2026-03-01", "motivo": "Férias",
    })
    assert db("SELECT 1 FROM inatividades") == []


@pytest.mark.xfail(
    strict=True,
    raises=ValueError,
    reason="BUG-005: mês/ano não numérico no formulário 'Gerar escala' "
    "derruba a requisição com erro 500 em vez de mostrar uma mensagem.",
)
def test_ct_adm_11_gerar_com_mes_invalido_nao_retorna_500(admin_client):
    resp = admin_client.post("/admin", data={"action": "gerar", "mes": "abc", "ano": "2026"})
    assert resp.status_code != 500
