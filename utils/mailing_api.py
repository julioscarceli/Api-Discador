# utils/mailing_api.py (VERSÃO INTEGRADA E COMPLETA)

import httpx
import pandas as pd
import os
import datetime
import json
from dotenv import load_dotenv
import base64
from io import StringIO, BytesIO
from datetime import datetime as dt  # Alias para evitar conflito com datetime
import re  # 🚨 NOVO: Para limpeza de PHP Notice

# Carrega variáveis de ambiente (necessário para os.getenv)
load_dotenv()

# --- CONSTANTES GLOBAIS ---
BASE_URL_MG = os.getenv("BASE_URL_MG", "http://186.194.50.155")
BASE_URL_SP = os.getenv("BASE_URL_SP", "https://186.194.50.149")
API_TOKEN = os.getenv("API_TOKEN")
SAIDAS_VALOR = os.getenv("SAIDAS_VALOR", "70")
FILA_NOME_MG = os.getenv("FILA_NOME_MG", "DISCADOR_MG")
FILA_NOME_SP = os.getenv("FILA_NOME_SP", "DISCADOR_SP")

if not API_TOKEN:
    print("ATENÇÃO: API_TOKEN não encontrado. As chamadas API falharão.")


# --- FUNÇÕES DE INFRAESTRUTURA E AUXILIARES ---

def get_base_url_for_api(server: str) -> str:
    """Retorna a URL base correta: http://IP/api/ (O caminho validado)."""
    if server.upper() == "SP":
        base = BASE_URL_SP
    else:
        base = BASE_URL_MG
    return f"{base.rstrip('/')}/api/"


def get_fila_name(server: str) -> str:
    """Retorna o nome da fila correto para a construção do CSV."""
    if server.upper() == "SP":
        return FILA_NOME_SP
    return FILA_NOME_MG


def extract_metrics(status_data, server_name):
    """Extrai os campos 'progresso' e 'saidas' de forma segura do JSON de status."""
    if not isinstance(status_data, dict) or status_data.get('status') == 'Erro':
        return {"progresso": "N/A", "saidas": "N/A"}
    progresso = status_data.get('progresso', 'N/D')
    try:
        saidas = status_data['dados'][0]['saidas']
    except (KeyError, IndexError):
        saidas = 'N/D'
    return {"progresso": progresso, "saidas": saidas}


# --- ATUALIZAÇÃO DA LINHA 1 (CONFIGURAÇÃO 2026 / 24H) ---
def _generate_metadata_line(campaign_id: str, mailling_name: str, server: str, login_crm: str = "AUTOMACAO") -> str:
    """Cria a primeira linha de metadados (15 colunas) garantindo discagem imediata."""
    data_hoje = dt.now().strftime('%Y-%m-%d')
    hora_agora = dt.now().strftime('%H:%M:%S')
    
    metadata = [
        str(campaign_id),                # Coluna A: ID da campanha
        str(mailling_name),              # Coluna B: Nome do Mailing
        str(SAIDAS_VALOR),               # Coluna C: Canais
        "sem",                           # Coluna D: Fila (URA Reversa usa 'sem')
        f"{data_hoje} {hora_agora}",     # Coluna E: Data/Hora
        str(login_crm),                  # Coluna F: Login CRM
        data_hoje,                       # Coluna G: Data inicial
        "2026-12-31",                    # Coluna H: Data final
        "00:00:01",                      # Coluna I: Hora inicial
        "23:59:59",                      # Coluna J: Hora final
        "1",                             # Coluna K: Tentativas
        "simultanea",                    # Coluna L: Velocidade
        "1,2,3,4,5,6,7",                 # Coluna M: Dias da semana
        "",                              # Coluna N: Audio
        ""                               # Coluna O: Opções URA
    ]
    return ";".join(metadata)


# --- ATUALIZAÇÃO DA TRANSFORMAÇÃO (LAYOUT SOLICITADO) ---
def _transform_client_data(file_content_base64: str, campaign_id: str, mailling_name: str, server: str,
                           login_crm: str) -> str:
    """Transforma o Base64 no layout Telefone, Nome, CPF, Livre1, Chave validados localmente."""
    try:
        decoded_bytes = base64.b64decode(file_content_base64)
        # Usamos BytesIO para ler o binário decodificado corretamente
        df_source = pd.read_csv(BytesIO(decoded_bytes), sep=';', encoding='latin-1', header=0, engine='python')
    except Exception as e:
        raise Exception(f"Falha na leitura do CSV: {e}")

    df_target = pd.DataFrame()
    # Mapeamento exato das colunas conforme seu teste local de sucesso
    df_target[0] = df_source.iloc[:, 29].astype(str).str.replace(r'\D', '', regex=True) # A: Numero
    df_target[1] = ""                                                                 # B: Vazio (Obrigatório)
    df_target[2] = df_source.iloc[:, 0].astype(str).str.slice(0, 50)                   # C: Nome
    df_target[3] = df_source.iloc[:, 1].astype(str).str.replace(r'\D', '', regex=True) # D: CPF
    df_target[4] = df_source.iloc[:, 2].fillna('').astype(str)                         # E: LIVRE1
    df_target[5] = df_source.iloc[:, 3].fillna('').astype(str)                         # F: CHAVE
    
    # Completa as 15 colunas obrigatórias
    for i in range(6, 15): 
        df_target[i] = ""

    metadata_line = _generate_metadata_line(campaign_id, mailling_name, server, login_crm)
    temp_target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_api_upload.csv")

    with open(temp_target_path, 'w', encoding='latin-1', newline='') as f:
        f.write(metadata_line + "\r\n")
        df_target.to_csv(f, sep=';', header=False, index=False, encoding='latin-1', lineterminator='\r\n')
    
    return temp_target_path


def _clean_php_output(response_text: str, server: str) -> str:
    """Limpa o output de PHP Notices e retorna apenas a string JSON."""
    json_start_match = re.search(r"(\{.*|\[.*)", response_text, re.DOTALL)
    if json_start_match:
        clean_json_text = json_start_match.group(1).strip()
        return clean_json_text
    return response_text


# --- 🚨 NOVA FUNÇÃO: CRIAÇÃO DE CAMPANHA (VINCULADOR) ---
async def api_create_campaign(server: str, mailing_name: str, cookies: dict):
    """
    Cria a campanha no discador e retorna o ID gerado conforme validado no Postman.
    """
    url = f"{get_base_url_for_api(server)}create_poll.php"
    
    # Limpa o nome do arquivo para usar como título
    titulo_limpo = mailing_name.replace(".csv", "").replace(".CSV", "")
    
    payload = {
        'token': API_TOKEN,
        'titulo': titulo_limpo,
        'descriçao': f"Gerada via API: {titulo_limpo}",
        'api': 'on',
        'url_api': "https://app.aquicob.com.br/index.php?a=acionamento&b=acionamento&pes_codigo={INFO1}&pop_up=1&loj_codigo={INFO2}"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(verify=False, cookies=cookies, headers=headers) as client:
        try:
            response = await client.post(url, data=payload, timeout=20.0)
            response_text_clean = _clean_php_output(response.text.strip(), server)
            dados = json.loads(response_text_clean)
            
            # Retorna o ID (ex: "205") se o sucesso for verdadeiro no JSON
            if dados.get("success") is True:
                return dados.get("id")
            return None
        except Exception as e:
            print(f"❌ Erro técnico ao criar campanha: {e}")
            return None


# --- API CALL 1: LISTAR CAMPANHAS (Mantida íntegra) ---
async def api_list_campaigns(server: str):
    """Lista todas as campanhas ativas."""
    url = f"{get_base_url_for_api(server)}list_campaign.php"
    data = {'token': API_TOKEN}
    async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
        response = await client.post(url, data=data)
        response.raise_for_status()
        response_text_clean = _clean_php_output(response.text.strip(), server)
        try:
            return json.loads(response_text_clean)
        except json.JSONDecodeError as e:
            raise Exception(f"API retornou formato inválido (não é JSON).") from e


# --- API CALL 2: OBTER STATUS DA CAMPANHA (Mantida íntegra) ---
async def api_get_campaign_status(server: str, campaign_id: str):
    """Obtém status detalhado de uma campanha (necessário para progresso)."""
    url = f"{get_base_url_for_api(server)}campaign_exec.php"
    params = {'id': campaign_id, 'token': API_TOKEN}
    async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        response_text_clean = _clean_php_output(response.text.strip(), server)
        try:
            return json.loads(response_text_clean)
        except json.JSONDecodeError as e:
            raise Exception(f"API retornou formato inválido (não é JSON).") from e


# --- MÉTRICAS GLOBAIS (Mantida íntegra) ---
async def get_active_campaign_metrics(server: str) -> dict:
    try:
        campaigns = await api_list_campaigns(server)
        if not campaigns or not campaigns[0].get('id'):
            return {"nome": "Nenhuma Campanha Ativa", "progresso": "0%", "saidas": "0", "id": None}
        active_campaign = campaigns[0]
        campaign_id = active_campaign.get('id')
        status_data = await api_get_campaign_status(server, campaign_id)
        metrics = extract_metrics(status_data, server)
        return {
            "nome": active_campaign.get('nome', 'N/A'),
            "progresso": metrics['progresso'],
            "saidas": metrics['saidas'],
            "id": campaign_id
        }
    except Exception as e:
        return {"nome": "ERRO API", "progresso": "N/A", "saidas": "N/A", "id": None}


# --- API CALL 3: UPLOAD MAILING (ATUALIZADO COM AS CHAVES VALIDALAS) ---
async def api_import_mailling_upload(server: str, campaign_id: str, file_content_base64: str, mailling_name: str,
                                     login_crm: str):
    """Envia o arquivo para a API usando as chaves validadas: file e import."""
    temp_file_path = None
    try:
        # 1. Transforma os dados usando as novas regras de layout
        temp_file_path = _transform_client_data(file_content_base64, campaign_id, mailling_name, server, login_crm)

        # 2. Configuração de envio conforme seu teste local integracao_local_final.py
        url = f"{get_base_url_for_api(server)}import_mailling.php"

        with open(temp_file_path, 'rb') as f:
            # CHAVE MÁGICA: O arquivo deve ser 'file' e o comando de texto deve ser 'import'
            files = {'file': ('upload.csv', f, 'text/csv')}
            data = {'token': API_TOKEN, 'import': 'ok'}

            async with httpx.AsyncClient(timeout=300.0, verify=False) as client:
                response = await client.post(url, data=data, files=files)
                response.raise_for_status()

            raw_response_text = response.text
            response_text_clean = _clean_php_output(raw_response_text.strip(), server)

            try:
                return json.loads(response_text_clean)
            except json.JSONDecodeError:
                raise Exception(f"RESPOSTA DO SERVIDOR: {raw_response_text[:500]}")

    except Exception as e:
        raise Exception(f"ERRO CRÍTICO NO UPLOAD: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)









