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
4. Execute a aplicação:
   ```bash
   python app.py
   ```

## Deploy no Heroku / plataforma compatível

```bash
gunicorn app:app
```
