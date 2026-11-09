"""Regras de negócio do algoritmo de geração de escala (CT-ESC)."""
from collections import Counter, defaultdict
from datetime import date, timedelta

import pytest

import app as app_module
from conftest import fins_de_semana

TURNO_DIA = "08:00 às 17:00"
TURNO_NOITE = "17:00 às 06:00"


def test_ct_esc_01_so_escala_sabados_domingos_e_feriados(escala_marco_2026):
    """Março/2026 não tem feriado nacional: só fins de semana entram."""
    dias = {r["data"] for r in escala_marco_2026}
    assert dias == set(fins_de_semana(3, 2026))


def test_ct_esc_02_retorna_quantidade_de_dias_escalados(db):
    assert app_module.gerar_escala_mes(3, 2026) == len(fins_de_semana(3, 2026))


def test_ct_esc_03_feriado_nacional_em_dia_util_entra_na_escala(db):
    app_module.gerar_escala_mes(4, 2026)  # 21/04/2026 (Tiradentes) é terça-feira
    dias = {r["data"] for r in db("SELECT DISTINCT data FROM fds")}
    assert date(2026, 4, 21) in dias


def test_ct_esc_04_feriado_estadual_sp_entra_na_escala(db):
    app_module.gerar_escala_mes(7, 2026)  # 09/07/2026 é quinta-feira
    dias = {r["data"] for r in db("SELECT DISTINCT data FROM fds")}
    assert date(2026, 7, 9) in dias


def test_ct_esc_05_feriado_manual_entra_na_escala(admin_client, db):
    admin_client.post("/admin", data={
        "action": "add_holiday", "holiday_date": "2026-03-19",
        "holiday_description": "Padroeiro de SJC",
    })
    app_module.gerar_escala_mes(3, 2026)
    dias = {r["data"] for r in db("SELECT DISTINCT data FROM fds")}
    assert date(2026, 3, 19) in dias


def test_ct_esc_06_cobertura_de_turnos_por_area(escala_marco_2026):
    """SJC e Taubaté: 2 turnos por dia. Litoral: só o turno diurno."""
    por_dia = defaultdict(lambda: defaultdict(set))
    for r in escala_marco_2026:
        por_dia[r["data"]][r["area"]].add(r["turno"])

    for dia, areas in por_dia.items():
        assert areas["SJC"] == {TURNO_DIA, TURNO_NOITE}, dia
        assert areas["TAUBATE"] == {TURNO_DIA, TURNO_NOITE}, dia
        assert areas["LITORAL"] == {TURNO_DIA}, dia


def test_ct_esc_07_tecnico_so_trabalha_na_propria_area(escala_marco_2026):
    for r in escala_marco_2026:
        assert r["area"] == r["area_tecnico"]


def test_ct_esc_08_mesmo_tecnico_nao_faz_dois_turnos_no_mesmo_dia(escala_marco_2026):
    contagem = Counter((r["data"], r["tecnico_id"]) for r in escala_marco_2026)
    assert max(contagem.values()) == 1


def test_ct_esc_09_mesmo_tecnico_nao_repete_turno_em_dias_seguidos(escala_marco_2026):
    por_slot = defaultdict(list)
    for r in escala_marco_2026:
        por_slot[(r["area"], r["turno"])].append((r["data"], r["tecnico_id"]))
    for slot, plantoes in por_slot.items():
        for (d1, t1), (d2, t2) in zip(plantoes, plantoes[1:]):
            if d2 - d1 == timedelta(days=1):
                assert t1 != t2, f"{slot}: técnico {t1} em {d1} e {d2}"


def test_ct_esc_10_distribuicao_justa_dentro_da_area(escala_marco_2026):
    """Diferença entre quem mais e quem menos trabalhou na área é de no máximo 1 plantão."""
    por_area = defaultdict(Counter)
    for r in escala_marco_2026:
        por_area[r["area"]][r["tecnico_id"]] += 1
    for area, contagem in por_area.items():
        assert max(contagem.values()) - min(contagem.values()) <= 1, (area, contagem)


def test_ct_esc_11_tecnico_inativo_nao_e_escalado(admin_client, db):
    tecnico = db("SELECT id, re FROM tecnicos WHERE area = 'SJC' ORDER BY nome LIMIT 1")[0]
    admin_client.post("/admin", data={
        "action": "add_inatividade", "tecnico_re": tecnico["re"],
        "data_inicio": "2026-03-01", "data_fim": "2026-03-31", "motivo": "Férias",
    })
    app_module.gerar_escala_mes(3, 2026)
    assert db("SELECT 1 FROM fds WHERE tecnico_id = %s", (tecnico["id"],)) == []


def test_ct_esc_12_inatividade_parcial_bloqueia_so_o_periodo(admin_client, db):
    tecnico = db("SELECT id, re FROM tecnicos WHERE area = 'LITORAL' ORDER BY nome LIMIT 1")[0]
    admin_client.post("/admin", data={
        "action": "add_inatividade", "tecnico_re": tecnico["re"],
        "data_inicio": "2026-03-01", "data_fim": "2026-03-15", "motivo": "Atestado",
    })
    app_module.gerar_escala_mes(3, 2026)
    datas = {r["data"] for r in db("SELECT data FROM fds WHERE tecnico_id = %s", (tecnico["id"],))}
    assert all(d > date(2026, 3, 15) for d in datas)


def test_ct_esc_13_regerar_o_mes_nao_duplica_registros(db):
    app_module.gerar_escala_mes(3, 2026)
    primeira = db("SELECT COUNT(*) AS n FROM fds")[0]["n"]
    app_module.gerar_escala_mes(3, 2026)
    segunda = db("SELECT COUNT(*) AS n FROM fds")[0]["n"]
    assert primeira == segunda == len(fins_de_semana(3, 2026)) * 5


def test_ct_esc_14_regerar_um_mes_nao_apaga_outro(db):
    app_module.gerar_escala_mes(3, 2026)
    app_module.gerar_escala_mes(4, 2026)
    meses = {r["m"] for r in db("SELECT DISTINCT EXTRACT(MONTH FROM data)::int AS m FROM fds")}
    assert meses == {3, 4}


def test_ct_esc_15_area_toda_inativa_nao_quebra_a_geracao(db):
    """Regressão do BUG-006 (corrigido)."""
    db("UPDATE tecnicos SET ativo = FALSE WHERE area = 'LITORAL'")
    app_module.gerar_escala_mes(3, 2026)
    assert db("SELECT 1 FROM fds WHERE area = 'LITORAL'") == []
    assert db("SELECT COUNT(*) AS n FROM fds WHERE area = 'SJC'")[0]["n"] > 0


def test_ct_esc_16_descanso_minimo_entre_noturno_e_diurno(db):
    """Ninguém faz 17h-06h num dia e 08h-17h no dia seguinte (só 2h de descanso).

    Hoje isso acontece por consequência do rodízio, não por uma regra explícita
    no código (ver RISCO-001 no TEST_PLAN.md). Este teste protege contra regressão.
    """
    for mes in range(1, 13):
        app_module.gerar_escala_mes(mes, 2026)
    plantoes = db("SELECT data, turno, tecnico_id FROM fds")
    noturnos = {(r["tecnico_id"], r["data"]) for r in plantoes if r["turno"] == TURNO_NOITE}
    for r in plantoes:
        if r["turno"] == TURNO_DIA:
            assert (r["tecnico_id"], r["data"] - timedelta(days=1)) not in noturnos
