import dash
from dash import dcc
from dash import html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import datetime
import time
import json
import random
import asyncio

# --- CONFIGURAÇÕES E INICIALIZAÇÃO ---
# 🚨 Em ambiente de produção, certifique-se de que utils/mailing_api.py está acessível
from utils.mailing_api import get_active_campaign_metrics

# Inicializa o Dash com o tema escuro (DARKLY) do Bootstrap
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

# Inicia o servidor web, usando o tema escuro (dbc.themes.DARKLY).







# O executor permite chamar funções síncronas/assíncronas sem travar o Dash
executor = ThreadPoolExecutor(max_workers=5)

# Ponte Assíncrona. Essencial para o projeto. Permite que as chamadas async def (API)
# rodem em threads separadas, evitando que o dashboard trave enquanto espera a resposta da rede.










# --- ESTRUTURA GLOBAL DE DADOS (CACHE) ---
DASHBOARD_DATA = {
    # Status em tempo real (Será preenchido pela primeira chamada à API)
    'current_status': {
        'MG': {"nome": "Aguardando API...", "progresso": "0%", "saidas": "0", "id": None},
        'SP': {"nome": "Aguardando API...", "progresso": "0%", "saidas": "0", "id": None}
    },
    'import_log': [],

    # Armazenamento do conteúdo Base64 para MG e SP
    'uploaded_content': {
        'MG': None,
        'SP': None
    },
    'uploaded_filename': {
        'MG': None,
        'SP': None
    }
}

# --- ESTILOS ---
UPLOAD_STYLE_BASE = {
    'width': '100%', 'height': '40px', 'lineHeight': '40px', 'borderWidth': '1px',
    'borderRadius': '5px', 'textAlign': 'center', 'transition': 'all 0.3s'
}
UPLOAD_STYLE_DASHED = {**UPLOAD_STYLE_BASE, 'borderStyle': 'dashed', 'borderColor': '#888'}
UPLOAD_STYLE_SUCCESS = {**UPLOAD_STYLE_BASE, 'borderStyle': 'solid', 'borderColor': 'green'}

# Cache Global. Armazena o conteúdo Base64 dos uploads (MG/SP)
# e o histórico de logs. É o estado de memória que o dashboard usa.








# ------------------------------------------------------------------
# 2. FUNÇÕES DE INFRAESTRUTURA (BRIDGE PARA ASYNC)
# ------------------------------------------------------------------

def run_async_task(coro):
    """Executa uma corotina em um thread (bridge para o httpx/asyncio)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# Envolve as funções async (API) para que o thread do Dash possa executá-las.



def get_active_campaign_metrics_sync(server: str):
    """Função SÍNCRONA que executa a chamada master de API para obter status real."""
    import asyncio  # Necessário dentro da função
    # Chama a função assíncrona real de coleta de métricas (Master API)
    try:
        return run_async_task(get_active_campaign_metrics(server))
    except Exception as e:
        print(f"ERRO CRÍTICO na coleta de métricas para {server}: {e}")
        return {"nome": "ERRO API", "progresso": "N/A", "saidas": "N/A", "id": None}



def execute_daily_import_sync(server: str, file_content_base64: str):
    """
    Função SÍNCRONA que dispara o Worker de Limpeza (Web Scraping) e Upload (API).
    ⚠️ EM PRODUÇÃO: Esta função chamará o script daily_mailing_worker.py,
    que contém a lógica de: finalize_campaign_only() -> api_import_mailling_upload()
    """

    # SIMULAÇÃO DA ROTINA COMPLETA:
    old_campaign_name = DASHBOARD_DATA['current_status'][server]['nome']
    old_campaign_progress = DASHBOARD_DATA['current_status'][server]['progresso']

    # Chamada real ao Worker (simulada aqui)
    time.sleep(2)

    status = "Sucesso" if random.random() > 0.1 else "Falha"

    # Simula a atualização do status global (Nova Campanha no ar)
    new_campaign_name = f"CAMPANHA_{server}_{datetime.datetime.now().strftime('%H%M')}"
    DASHBOARD_DATA['current_status'][server]['nome'] = new_campaign_name
    DASHBOARD_DATA['current_status'][server]['progresso'] = '0%'
    DASHBOARD_DATA['current_status'][server]['saidas'] = random.choice(['70', '80'])

    # Registra o Log de Performance (Progresso Final)
    DASHBOARD_DATA['import_log'].insert(0, {
        'data': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'servidor': server,
        'mailing': new_campaign_name,  # Nome da campanha que foi importada
        'status': status,
        'progresso_final': old_campaign_progress  # Progresso da campanha que SAIU
    })

    # Limpa o cache após a importação
    DASHBOARD_DATA['uploaded_content'][server] = None
    DASHBOARD_DATA['uploaded_filename'][server] = None
    return "Importação concluída"


# ------------------------------------------------------------------
# 3. LAYOUT DASHBOARD
# ------------------------------------------------------------------

def create_info_card(title, value, server):
    """Cria um cartão de informação padronizado."""
    is_mg = server == 'MG'
    color = "success" if is_mg else "danger"

    return dbc.Card(
        dbc.CardBody([
            html.H5(title, className="card-title"),
            html.P(value, className="card-text fs-4 fw-bold"),
        ]),
        color=color,
        outline=True,
        className="text-center my-2"
    )


app.layout = dbc.Container([
    html.H1("🚀 Agendador Discador", className="my-4 text-center text-primary"),
    html.Hr(className="bg-light"),

    dcc.Interval(id='interval-component', interval=10 * 1000, n_intervals=0),

    dbc.Row([

        # COLUNA 1: CONTROLES E STATUS ATUAL
        dbc.Col(
            html.Div(id='controls-and-status', children=[
                html.H4("⚡ Controles de Ação", className="text-warning"),

                # UPLOAD MG (MAILING EMP)
                html.Label("Mailing EMP (MG) - Arraste e Solte", className="text-light mt-3"),
                dcc.Upload(
                    id='upload-data-mg',
                    children=html.Div(['Clique ou Arraste o CSV para Importação MG']),
                    style={**UPLOAD_STYLE_DASHED, 'borderColor': 'green'},
                    multiple=False
                ),
                html.Div(id='upload-status-mg', children=html.P("Aguardando CSV MG...", className="text-muted"),
                         style={'marginTop': '5px', 'marginBottom': '10px'}),

                # UPLOAD SP (MAILING CARD)
                html.Label("Mailing CARD (SP) - Arraste e Solte", className="text-light mt-3"),
                dcc.Upload(
                    id='upload-data-sp',
                    children=html.Div(['Clique ou Arraste o CSV para Importação SP']),
                    style={**UPLOAD_STYLE_DASHED, 'borderColor': 'red'},
                    multiple=False
                ),
                html.Div(id='upload-status-sp', children=html.P("Aguardando CSV SP...", className="text-muted"),
                         style={'marginTop': '5px', 'marginBottom': '10px'}),

                # Botão de Limpar Upload
                dbc.Button("Limpar Uploads", id="btn-clear-upload", color="secondary", className="w-100 mb-3"),

                # Botões de Importação
                dbc.Button("Importar MG (Manual)", id="btn-import-mg", color="success", className="w-100 mb-2"),
                dbc.Button("Importar SP (Manual)", id="btn-import-sp", color="danger", className="w-100 mb-4"),

                html.Div(id='import-status-output', style={'display': 'none'}),

                html.H4("✅ Status Atual do Discador", className="text-info mt-4"),
                html.Div(id='realtime-status'),
            ]),
            width=6
        ),

        # COLUNA 2: LOGS E HISTÓRICO DE IMPORTAÇÕES
        dbc.Col(
            html.Div(id='logs-and-history', children=[
                html.H4("📜 Histórico de Importações", className="text-info"),
                html.Div(id='log-table-output'),
            ]),
            width=6
        ),
    ], className="g-4"),

    html.Footer(
        html.P(f"Última Atualização: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", id='footer-timestamp',
               className="text-center text-secondary mt-5")
    )
], fluid=True)


# ------------------------------------------------------------------
# 4. CALLBACKS: LÓGICA DE INTERFACE E WORKER
# ------------------------------------------------------------------

# --- LÓGICA DE UPLOAD E LIMPEZA (Callbacks de Upload e Clear) ---

# (Os callbacks handle_upload_mg, handle_upload_sp e handle_clear_upload foram omitidos
# por serem longos, mas devem ser reintroduzidos aqui.)


# --- CALLBACK DE IMPORTAÇÃO (BOTÕES) ---
@app.callback(
    Output('import-status-output', 'children'),
    [Input('btn-import-mg', 'n_clicks'),
     Input('btn-import-sp', 'n_clicks')]
)
def handle_import_buttons(n_mg, n_sp):
    changed_id = [p['prop_id'] for p in dash.callback_context.triggered][0]

    if changed_id == '.':
        return html.Div(style={'display': 'none'})

    server_to_import = None
    if 'btn-import-mg' in changed_id and n_mg > 0:
        server_to_import = 'MG'
    elif 'btn-import-sp' in changed_id and n_sp > 0:
        server_to_import = 'SP'

    if server_to_import:
        file_content = DASHBOARD_DATA['uploaded_content'][server_to_import]
        filename = DASHBOARD_DATA['uploaded_filename'][server_to_import]

        if file_content is None:
            return dbc.Alert(f'❌ ERRO: Por favor, arraste o arquivo CSV para o campo de {server_to_import} primeiro.',
                             color="danger")
        # Validação Crítica. Verifica se o callback de upload (a parte omitida)
        # conseguiu armazenar a string Base64 do arquivo no cache.
        # Se o arquivo estiver faltando,
        # exibe um alerta de erro (dbc.Alert) na tela, protegendo a rotina de falhas no Worker.



        # Disparo do Worker no threadpool
        executor.submit(execute_daily_import_sync, server_to_import, file_content)

        return dbc.Alert(
            f'Importação de {filename} para {server_to_import} disparada. Verifique o Histórico.',
            color="success",
            className="mt-3"
        )

    return html.Div(style={'display': 'none'})
#  Detecção de Clique. O Dash descobre qual botão (btn-import-mg ou btn-import-sp) disparou o callback.
#  Garante que a lógica use o arquivo e o IP do servidor correto (MG ou SP).





# --- CALLBACK DE ATUALIZAÇÃO DE STATUS EM TEMPO REAL ---
@app.callback(
    [Output('realtime-status', 'children'),
     Output('footer-timestamp', 'children')],
    [Input('interval-component', 'n_intervals')]
    #Gatilho Automático. É o cronômetro que força a função a ser executada a cada 10 segundos.
    # Permite a monitoração contínua.
)
def update_realtime_status(n):
    # 1. Busca os dados dos Workers (em um thread separado)
    mg_data = executor.submit(get_active_campaign_metrics_sync, 'MG').result()
    #Coleta de Métricas. Chama a função get_active_campaign_metrics_sync
    # (que contém o código validado de API Call 1 e 2) em um thread.
    # Busca os dados reais de Nome da Campanha, Progresso e Saídas Ativas diretamente do servidor de discagem.
    sp_data = executor.submit(get_active_campaign_metrics_sync, 'SP').result()

    # 2. Cria os cartões de status
    cards = [
        dbc.Row([
            dbc.Col(create_info_card("Mailing Ativo MG", mg_data['nome'], 'MG'), md=12),
        ]),
        dbc.Row([
            dbc.Col(create_info_card("Progresso MG", mg_data['progresso'], 'MG'), md=6),
            dbc.Col(create_info_card("Saídas MG", mg_data['saidas'], 'MG'), md=6),
        ]),
        html.Hr(className="bg-secondary"),
        dbc.Row([
            dbc.Col(create_info_card("Mailing Ativo SP", sp_data['nome'], 'SP'), md=12),
        ]),
        dbc.Row([
            dbc.Col(create_info_card("Progresso SP", sp_data['progresso'], 'SP'), md=6),
            dbc.Col(create_info_card("Saídas SP", sp_data['saidas'], 'SP'), md=6),
        ])
    ]

    timestamp = f"Última Atualização: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    return cards, timestamp


# --- CALLBACK DE ATUALIZAÇÃO DA TABELA DE LOG (COM CORREÇÃO DE CRASH) ---
@app.callback(
    Output('log-table-output', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('import-status-output', 'children')]
)
def update_log_table(n_intervals, import_output):
    if not DASHBOARD_DATA['import_log']:
        return dbc.Alert("Nenhum registro de importação encontrado.", color="info")

    df = pd.DataFrame(DASHBOARD_DATA['import_log'])

    # Renomeia colunas para exibição amigável
    df.columns = ['Data/Hora', 'Servidor', 'Mailing', 'Status', 'Progresso Antigo']

    # Formatação de estilo do Dash Table
    table = dbc.Table.from_dataframe(
        df,
        striped=True,
        bordered=True,
        hover=True,
        dark=True,
        className="table-sm"
    )

    return table


# ------------------------------------------------------------------
# 5. EXECUÇÃO
# ------------------------------------------------------------------

if __name__ == '__main__':
    print("Iniciando servidor Dash...")
    app.run(debug=True)