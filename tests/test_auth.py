"""Autenticação e controle de acesso (CT-AUT)."""
import pytest


def test_ct_aut_01_pagina_de_login_carrega(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"<form" in resp.data


def test_ct_aut_02_login_valido_redireciona_para_admin(client):
    resp = client.post("/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin")


@pytest.mark.parametrize(
    "usuario,senha",
    [("admin", "errada"), ("naoexiste", "admin123"), ("", "")],
    ids=["senha-errada", "usuario-inexistente", "campos-vazios"],
)
def test_ct_aut_03_login_invalido_nao_autentica(client, usuario, senha):
    resp = client.post("/login", data={"username": usuario, "password": senha})
    assert resp.status_code == 200
    assert "Usuário ou senha inválidos".encode() in resp.data
    assert client.get("/admin").status_code == 302


def test_ct_aut_04_admin_sem_sessao_redireciona_para_login(client):
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_ct_aut_05_logout_encerra_a_sessao(admin_client):
    assert admin_client.get("/admin").status_code == 200
    resp = admin_client.get("/logout")
    assert resp.status_code == 302
    assert admin_client.get("/admin").status_code == 302


def test_ct_aut_06_sql_injection_no_login_nao_autentica(client):
    resp = client.post(
        "/login", data={"username": "admin' --", "password": "qualquer"}
    )
    assert resp.status_code == 200
    assert client.get("/admin").status_code == 302


def test_ct_aut_07_usuario_sem_permissao_nao_acessa_admin(client, usuario_comum):
    """Regressão do BUG-001 (corrigido)."""
    client.post("/login", data=usuario_comum)
    resp = client.get("/admin")
    assert resp.status_code in (302, 403)


def test_ct_aut_08_dashboard_reconhece_usuario_logado(admin_client):
    """Regressão do BUG-002 (corrigido)."""
    with admin_client.session_transaction() as sess:
        assert sess.get("logged_in") is True


def test_ct_aut_09_usuario_sem_permissao_vai_para_o_dashboard(client, usuario_comum):
    resp = client.post("/login", data=usuario_comum)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    with client.session_transaction() as sess:
        assert sess.get("is_admin") is False
