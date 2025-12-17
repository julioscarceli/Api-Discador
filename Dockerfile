# Usa imagem oficial do Playwright
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Instala bibliotecas do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala navegadores e dependências de sistema
RUN playwright install chromium --with-deps

# Copia o código do projeto
COPY . .

# Expõe a porta do FastAPI
EXPOSE 8000
