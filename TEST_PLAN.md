# Plano e registro de testes — Gerenciador de Escalas

| | |
|---|---|
| **Sistema** | Gerenciador de Escalas de plantão de fim de semana (Flask + PostgreSQL) |
| **Versão testada** | Release 1.8.3 (`master`) + correções de BUG-001 a BUG-007 |
| **Responsável** | Filipe Santos |
| **Data** | 09/11/2026 |
| **Ferramentas** | pytest, pytest-cov, Flask test client, PostgreSQL 16, GitHub Actions |
| **Resultado** | 67 casos · 67 aprovados · 7 defeitos encontrados e corrigidos · cobertura de `app.py`: 87% |

---

## 1. Objetivo

Garantir que a escala de plantão gerada automaticamente respeita as regras de negócio
(cobertura por área, rodízio justo, inatividades e feriados) e que o painel administrativo
só pode ser usado por quem tem permissão.

## 2. Escopo

**Dentro do escopo**
- Autenticação e controle de acesso (`/login`, `/logout`, `/admin`)
- Algoritmo `gerar_escala_mes()` — regras de negócio
- Painel administrativo: gerar escala, feriados manuais, inatividades, troca manual
- Dashboard público: navegação entre meses e validação de parâmetros

**Fora do escopo (nesta versão)**
- Layout e responsividade dos templates (testes visuais / E2E com Playwright: próxima etapa)
- Disponibilidade da BrasilAPI (é substituída por dados fixos nos testes)
- Desempenho e carga

## 3. Estratégia

| Nível | Como | Por quê |
|---|---|---|
| Unidade / regra de negócio | Chamada direta a `gerar_escala_mes()` e consulta ao banco | Valida o algoritmo isolado da interface |
| Integração | Flask test client + PostgreSQL real | Valida rota → banco → resposta, igual à produção |
| Regressão contínua | GitHub Actions a cada push e pull request | Nenhuma mudança entra sem rodar a suíte |

**Decisões técnicas**
- **Banco real, não mock:** o app usa recursos do PostgreSQL (`ON CONFLICT`, `EXTRACT`), então os testes usam PostgreSQL 16, local ou como *service container* no CI.
- **Isolamento:** antes de cada teste, as tabelas de escala, inatividades e feriados são zeradas (`TRUNCATE`).
- **Determinismo:** a API de feriados é substituída por uma lista fixa, sem dependência de rede.
- **Defeitos conhecidos ficam registrados no código:** cada bug tem um teste marcado como `xfail(strict=True)`. A suíte continua verde, o defeito fica visível no relatório e, quando for corrigido, o teste passa a falhar como *XPASS*, avisando que a marcação pode ser removida.

## 4. Como executar

```bash
# 1. Banco de testes (exemplo com Docker)
docker run -d --name pg-escalas -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=escalas_test -p 5432:5432 postgres:16

# 2. Dependências
pip install -r requirements-dev.txt

# 3. Testes + cobertura
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/escalas_test
pytest --cov=app --cov-report=term
```

No GitHub, o workflow **Tests** (`.github/workflows/tests.yml`) roda a mesma suíte e publica
o relatório JUnit e a cobertura HTML como artefato da execução.

---

## 5. Casos de teste

Legenda: ✅ aprovado · 🔧 aprovado após correção do defeito encontrado pelo teste

### 5.1 Autenticação e acesso — `tests/test_auth.py`

| ID | Cenário | Resultado esperado | Status |
|---|---|---|---|
| CT-AUT-01 | Abrir `/login` | Página com formulário (200) | ✅ |
| CT-AUT-02 | Login com credenciais válidas | Redireciona para `/admin` | ✅ |
| CT-AUT-03 | Login com senha errada, usuário inexistente e campos vazios (3 variações) | Mensagem de erro, sem sessão | ✅ |
| CT-AUT-04 | Acessar `/admin` sem login | Redireciona para `/login` | ✅ |
| CT-AUT-05 | Logout | Sessão encerrada; `/admin` volta a exigir login | ✅ |
| CT-AUT-06 | Tentativa de SQL injection no usuário (`admin' --`) | Login negado | ✅ |
| CT-AUT-07 | Usuário **sem** permissão de admin acessa `/admin` | Acesso negado (302/403) | 🔧 BUG-001 |
| CT-AUT-08 | Sessão após login indica usuário logado | `logged_in = True` | 🔧 BUG-002 |
| CT-AUT-09 | Login de usuário sem permissão | Vai para o dashboard, sem acesso ao painel | ✅ |

### 5.2 Dashboard público — `tests/test_dashboard_months.py`

| ID | Cenário | Resultado esperado | Status |
|---|---|---|---|
| CT-DSH-01 | `GET /health` | `{"status": "ok"}` | ✅ |
| CT-DSH-02 | Dashboard sem login | 200 | ✅ |
| CT-DSH-03 | `?mes=3&ano=2026` | Título "Março/2026" | ✅ |
| CT-DSH-04 | Mês inválido: 0, 13, -1, 99 (4 variações) | Volta para o mês atual sem erro | ✅ |
| CT-DSH-05 | Parâmetros não numéricos (`mes=abc`) | Página carrega sem erro | ✅ |
| CT-DSH-06 | Links de mês anterior/próximo: jan, dez e meio do ano (3 variações) | Virada de ano correta | ✅ |
| CT-DSH-07 | Escala gerada aparece no dashboard | Turnos exibidos | ✅ |
| CT-DSH-08 | Consultar um ano futuro (ano atual + 5) | Título com o ano pedido | 🔧 BUG-003 |
| CT-DSH-09 | Ano absurdo: 1900, 9999, -1 (3 variações) | Volta para o ano atual sem erro | ✅ |
| CT-DSH-10 | Usuário sem permissão tenta abrir `/admin` | Aviso "Acesso restrito" exibido no dashboard | ✅ |

### 5.3 Regras do algoritmo de escala — `tests/test_escala.py`

| ID | Regra validada | Status |
|---|---|---|
| CT-ESC-01 | Só sábados, domingos e feriados entram na escala | ✅ |
| CT-ESC-02 | A função retorna a quantidade de dias escalados | ✅ |
| CT-ESC-03 | Feriado nacional em dia útil (Tiradentes, terça) entra na escala | ✅ |
| CT-ESC-04 | Feriado estadual de SP (9 de julho) entra na escala | ✅ |
| CT-ESC-05 | Feriado cadastrado manualmente entra na escala | ✅ |
| CT-ESC-06 | SJC e Taubaté: 2 turnos por dia; Litoral: só o diurno | ✅ |
| CT-ESC-07 | Técnico só é escalado na própria área | ✅ |
| CT-ESC-08 | Ninguém faz dois turnos no mesmo dia | ✅ |
| CT-ESC-09 | Ninguém repete o mesmo turno em dias seguidos | ✅ |
| CT-ESC-10 | Distribuição justa: diferença máxima de 1 plantão entre técnicos da mesma área | ✅ |
| CT-ESC-11 | Técnico inativo no mês inteiro não é escalado | ✅ |
| CT-ESC-12 | Inatividade parcial bloqueia só o período informado | ✅ |
| CT-ESC-13 | Gerar o mesmo mês duas vezes não duplica registros | ✅ |
| CT-ESC-14 | Gerar um mês não apaga a escala de outro mês | ✅ |
| CT-ESC-15 | Área inteira inativa não impede a geração das outras áreas | 🔧 BUG-006 |
| CT-ESC-16 | Ninguém faz noturno (17h–06h) seguido de diurno (08h–17h) no dia seguinte | ✅ (ver RISCO-001) |

### 5.4 Painel administrativo — `tests/test_admin_features.py`

| ID | Cenário | Resultado esperado | Status |
|---|---|---|---|
| CT-ADM-01 | Abrir painel logado como admin | 200 | ✅ |
| CT-ADM-02 | Gerar escala pelo formulário | Mensagem de sucesso e registros no banco | ✅ |
| CT-ADM-03 | Cadastrar feriado manual | Feriado salvo com descrição | ✅ |
| CT-ADM-04 | Cadastrar a mesma data duas vezes | Atualiza a descrição, sem duplicar | ✅ |
| CT-ADM-05 | Remover feriado manual | Registro excluído | ✅ |
| CT-ADM-06 | Registrar inatividade para vários técnicos de uma vez | Um registro por técnico | ✅ |
| CT-ADM-07 | Remover inatividade | Registro excluído | ✅ |
| CT-ADM-08 | Troca manual de técnico em um plantão | Plantão passa para o novo técnico | ✅ |
| CT-ADM-09 | Troca manual com RE inexistente | Mensagem de erro; plantão inalterado | ✅ |
| CT-ADM-10 | Inatividade com data final antes da inicial | Rejeitada com mensagem | 🔧 BUG-004 |
| CT-ADM-11 | Gerar escala com mês/ano inválido: texto, 13, 0, ano fora da janela, vazio (6 variações) | Mensagem de erro, nada gerado, sem erro 500 | 🔧 BUG-005 |
| CT-ADM-12 | Inatividade sem data de início, sem data de fim ou em formato inválido (3 variações) | Rejeitada com mensagem | ✅ |
| CT-ADM-13 | Inatividade de um único dia (início = fim) | Aceita | ✅ |
| CT-ADM-14 | Painel com `mes`/`ano` inválidos na URL (3 variações) | Painel abre no mês atual, sem erro | 🔧 BUG-007 |

---

## 6. Defeitos encontrados

| ID | Severidade | Resumo | Teste | Situação |
|---|---|---|---|---|
| BUG-001 | 🔴 Alta (segurança) | Usuário sem permissão acessava o painel admin | CT-AUT-07 | ✅ Corrigido |
| BUG-006 | 🔴 Alta | Uma área sem técnicos ativos impedia a geração da escala inteira | CT-ESC-15 | ✅ Corrigido |
| BUG-002 | 🟠 Média | Dashboard não reconhecia o usuário logado | CT-AUT-08 | ✅ Corrigido |
| BUG-005 | 🟠 Média | Mês/ano inválido no formulário causava erro 500 | CT-ADM-11 | ✅ Corrigido |
| BUG-007 | 🟠 Média | Painel admin com `mes=13` na URL causava erro 500 | CT-ADM-14 | ✅ Corrigido |
| BUG-004 | 🟡 Baixa | Período de inatividade invertido era aceito | CT-ADM-10 | ✅ Corrigido |
| BUG-003 | 🟡 Baixa | Dashboard limitado aos anos 2020–2030 | CT-DSH-08 | ✅ Corrigido |

### BUG-001 — Painel admin acessível sem permissão de administrador ✅ Corrigido
- **Causa:** a rota `/admin` só verificava se havia uma chave `admin` na sessão, gravada para qualquer usuário válido.
- **Correção:** o login passou a gravar `logged_in`, `username` e `is_admin`. A rota `/admin` exige `is_admin`; usuários sem permissão voltam ao dashboard com aviso, e o botão "Admin" só aparece para administradores.
- **Regressão:** CT-AUT-07 e CT-AUT-09.

### BUG-006 — Área sem técnicos ativos quebrava a geração da escala ✅ Corrigido
- **Passos:** desativar ou colocar de férias todos os técnicos de uma área (ex.: Litoral) → gerar a escala do mês.
- **Obtido antes da correção:** `IndexError: list index out of range` em `sortear_tecnico()`. Nenhuma área era escalada.
- **Correção:** quando não há técnico disponível na área naquele dia, o turno é pulado e um aviso vai para o log; as demais áreas são escaladas normalmente.
- **Regressão:** CT-ESC-15.

### BUG-002 — Dashboard não reconhecia o usuário logado ✅ Corrigido
- **Causa:** `is_logged_in()` lia `session["logged_in"]`, que nunca era gravado, e `is_admin()` devolvia o nome do usuário em vez de um booleano.
- **Correção:** chaves de sessão padronizadas junto com o BUG-001.
- **Regressão:** CT-AUT-08.

### BUG-005 — Erro 500 com mês/ano inválido ao gerar escala ✅ Corrigido
- **Passos:** enviar o formulário "Gerar escala" com `mes=abc`.
- **Obtido antes da correção:** `ValueError` em `int(request.form.get("mes"))`, fora do `try`, e erro 500.
- **Correção:** leitura com `request.form.get("mes", type=int)` e validação de mês (1–12) e ano; valores inválidos mostram uma mensagem e nada é gerado.
- **Regressão:** CT-ADM-11 (6 variações).

### BUG-007 — Painel admin com mês inválido na URL ✅ Corrigido
- **Encontrado por:** CT-ADM-14, escrito durante a correção do BUG-005.
- **Passos:** abrir `/admin?mes=13`.
- **Obtido antes da correção:** erro 500 ao calcular o "próximo mês" (`date(ano, 14, 1)`).
- **Correção:** o painel usa a mesma validação de mês e ano do dashboard.

### BUG-004 — Inatividade com período invertido ✅ Corrigido
- **Passos:** registrar inatividade com início 20/03 e fim 01/03.
- **Obtido antes da correção:** registro salvo; ele nunca bloqueava nenhum dia e confundia quem consultava.
- **Correção:** o servidor exige as duas datas em formato válido e `data_fim >= data_inicio`; caso contrário, mostra uma mensagem e não grava nada.
- **Regressão:** CT-ADM-10, CT-ADM-12 e CT-ADM-13.

### BUG-003 — Anos depois de 2030 eram ignorados ✅ Corrigido
- **Passos:** abrir `/?mes=1&ano=2031`.
- **Obtido antes da correção:** o ano era trocado silenciosamente pelo ano atual.
- **Correção:** a validação usa uma janela relativa ao ano atual (10 anos para trás e para frente), que não envelhece.
- **Regressão:** CT-DSH-08 e CT-DSH-09.

---

## 7. Riscos e observações

- **RISCO-001 — Descanso entre turnos.** O código só impede repetir o *mesmo* turno em dias seguidos. Fazer noturno no sábado (até 06h) e diurno no domingo (08h) não acontece hoje, mas por efeito do rodízio, não de uma regra. O CT-ESC-16 protege contra regressão; o ideal é tornar a regra explícita no algoritmo.
- **RISCO-002 — Credenciais.** Senhas ficam em texto puro no banco, existe um usuário `admin` criado com senha padrão no código e a `SECRET_KEY` tem um valor padrão no código. Recomendado: hash de senha (`werkzeug.security`), senha do admin trocada em produção e `SECRET_KEY` obrigatória por variável de ambiente.
- **RISCO-003 — Dados pessoais no código.** Nomes e REs dos técnicos estão no código-fonte público. O ideal é carregá-los de um arquivo fora do repositório ou só pelo painel.
- **RISCO-004 — Feriado de 25 de janeiro.** A lista `FERIADOS_SP` inclui 25/01, que é o aniversário da **cidade** de São Paulo, não feriado estadual. Vale confirmar com a operação se ele deve gerar plantão em SJC, Taubaté e Litoral.
- **RISCO-005 — Dependência externa a cada acesso.** O dashboard consulta a BrasilAPI a cada carregamento (timeout de 10 s), sem cache. Se a API ficar lenta, o dashboard fica lento.

## 8. Próximos passos

1. Tratar os riscos RISCO-002 (senhas com hash) e RISCO-003 (dados pessoais fora do código).
2. Testes E2E com Playwright: login, geração da escala e troca manual pelo navegador.
3. Tornar explícita no algoritmo a regra de descanso entre turnos (RISCO-001).
