# Gerenciador de Escalas

Aplicação Flask para geração e administração de escalas de plantão e expediente.

## Como executar

1. Crie um ambiente virtual Python:
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure as variáveis de ambiente:
   - `DATABASE_URL`
   - `SECRET_KEY`
   - `SP_SCHOOL_HOLIDAYS` (opcional) — datas adicionais de feriados escolares de São Paulo no formato `YYYY-MM-DD,YYYY-MM-DD`
4. Execute a aplicação:
   ```bash
   python app.py
   ```

## Comportamento de feriados

- A aplicação agora consulta a API pública de feriados nacionais do Brasil para São Paulo.
- Também inclui os feriados estaduais de São Paulo configurados no código, como a Revolução Constitucionalista em 2026.
- Se você quiser incluir feriados escolares específicos, use a variável `SP_SCHOOL_HOLIDAYS`.

## Deploy no Heroku / plataforma compatível

```bash
gunicorn app:app
```
