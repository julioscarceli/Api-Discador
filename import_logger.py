from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from datetime import datetime

app = FastAPI()

# Permite que o front-end (Lovable) envie dados para este worker
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/logs/import")
async def receive_log(request: Request):
    data = await request.json()
    
    timestamp = data.get("timestamp", datetime.now().strftime("%H:%M:%S"))
    region = data.get("region", "??")
    action = data.get("action", "ACAO")
    status = data.get("status", "INFO")
    message = data.get("message", "")
    file_name = data.get("file_name", "N/A")
    campaign_id = data.get("campaign_id", "N/A")

    # Ícone visual para o log do Railway
    status_icon = "✅" if status == "sucesso" else "❌" if status == "erro" else "⏳"
    
    log_line = (
        f"{status_icon} [{timestamp}] [{region}] {action.upper()} | "
        f"Arquivo: {file_name} | ID Campanha: {campaign_id} | Msg: {message}"
    )
    
    print(log_line) # Isso aparecerá nos Deploy Logs do Railway
    return {"status": "success"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
