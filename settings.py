# config/settings.py (VERSÃO FINAL DE DEPLOY COERENTE)

# --- URLs de Acesso ao SISTEMA (Para Login/Web Scraping) ---
# Necessárias para o monitor.py e restart_campaign.py.
LOGIN_URL_MG = "http://186.194.50.155/azcall/pages/login.php"
LOGIN_URL_SP = "https://186.194.50.149/azcall/pages/login.php"

# --- URLs Base da API (Usadas para construir o endpoint /api/) ---
# O Postman e testes provaram que a API está acessível na raiz do IP.
BASE_URL_MG = "http://186.194.50.155"
BASE_URL_SP = "https://186.194.50.149"


# --- CONFIGURAÇÕES DO NEGÓCIO ---
FILA_NOME_MG = "DISCADOR_MG"
FILA_NOME_SP = "DISCADOR_SP"
SAIDAS_VALOR = "70" # Valor de canais para o upload diário



# --- CONTROLE DE SEGURANÇA ---
API_TOKEN_NAME = "API_TOKEN" # Chave lida do Railway Secrets/Local .env


# --- CAMINHOS DE MAILING LOCAIS (TESTE) ---
LOCAL_MAILING_BASE_DIR = r"D:\Ferramentas\5. Verificação Final\MAILING DISCADOR"
