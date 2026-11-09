# Gerenciador de Escalas

[![Tests](https://github.com/Filipe-Bina/gerenciador_escalas/actions/workflows/tests.yml/badge.svg)](https://github.com/Filipe-Bina/gerenciador_escalas/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)

> **EN:** Weekend on-call rotation manager for field-technician teams. Automatically builds a fair monthly schedule across three regions, honouring holidays and time off, with an admin panel for manual adjustments. Covered by a 51-case pytest suite running on GitHub Actions.

Sistema web que gera e publica a escala de plantão de fim de semana e feriados das equipes técnicas de **SJC**, **Taubaté** e **Litoral**. Está em uso pela operação.

## Funcionalidades

- **Geração automática da escala do mês**
  - SJC e Taubaté: turnos 08h–17h e 17h–06h; Litoral: turno 08h–17h
  - Só sábados, domingos e feriados (nacionais via BrasilAPI, estaduais de SP e feriados cadastrados manualmente)
  - Rodízio justo: quem trabalhou menos no ano é escalado primeiro
  - Ninguém faz dois turnos no mesmo dia nem repete o mesmo turno em dias seguidos
  - Técnicos em férias, folga ou atestado ficam fora da escala
- **Painel administrativo:** gerar escala, cadastrar feriados, registrar inatividades e trocar o técnico de um plantão
- **Dashboard público:** calendário do mês e destaque do próximo fim de semana

## Stack

Python · Flask · PostgreSQL · Gunicorn · pytest · GitHub Actions

## Rodando localmente

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://usuario:senha@localhost:5432/escalas
export SECRET_KEY=uma-chave-forte
flask --app app run
```

As tabelas são criadas automaticamente na primeira execução.

## Testes

A suíte tem **51 casos** (regras de negócio, integração com o banco e controle de acesso) e roda contra um PostgreSQL real.

```bash
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/escalas_test
pytest --cov=app
```

Resultado atual: **48 aprovados · 3 defeitos abertos registrados · 86% de cobertura de `app.py`**. Os testes já encontraram e ajudaram a corrigir uma falha de controle de acesso e um erro que travava a geração da escala.

O plano de testes, os casos de teste e os relatórios de defeitos estão em **[TEST_PLAN.md](TEST_PLAN.md)**.

## Estrutura

```
app.py                     # rotas, algoritmo de escala e acesso ao banco
templates/                 # login, dashboard e painel admin
tests/
  conftest.py              # fixtures: banco limpo, cliente autenticado, feriados fixos
  test_auth.py             # autenticação e controle de acesso
  test_escala.py           # regras do algoritmo de escala
  test_admin_features.py   # painel administrativo
  test_dashboard_months.py # dashboard e navegação entre meses
.github/workflows/tests.yml
```
