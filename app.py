from flask import Flask, request, jsonify
from openai import OpenAI
import requests
import sqlite3
import json
import os

# =====================
# CONFIGURAÇÕES
# =====================

TELEGRAM_BOT_TOKEN = ""
OPENAI_API_KEY = ""

DATABASE = "gastos.db"

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)

# =====================
# BANCO DE DADOS do 
# =====================

def conectar_db():
    return sqlite3.connect(DATABASE)

def criar_tabela():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            valor REAL,
            categoria TEXT,
            descricao TEXT
        )
    """)
    conn.commit()
    conn.close()

def salvar_gasto(chat_id, valor, categoria, descricao):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO gastos (chat_id, valor, categoria, descricao) VALUES (?, ?, ?, ?)",
        (chat_id, valor, categoria, descricao)
    )
    conn.commit()
    conn.close()

# =====================
# HOME
# =====================

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "Serviço funcionando"})

# =====================
# OPENAI - INTERPRETAR GASTO
# =====================

import re

def interpretar_gasto(mensagem):
    texto = mensagem.lower()


    # 1️⃣ Tentativa simples (rápida e confiável)
    match = re.search(r'(\d+[.,]?\d*)', texto)
    if match:
        valor = float(match.group(1).replace(",", "."))
        descricao = texto.replace(match.group(0), "").strip()
        descricao = descricao.replace("gastei", "").replace("reais", "").strip()

        return {
            "valor": valor,
            "categoria": "geral",
            "descricao": descricao or "gasto"
        }

    # 2️⃣ Fallback OpenAI (casos complexos)
    response = client.responses.create(
        model="gpt-4o-mini",
        input=f"""
Extraia os dados do gasto abaixo e retorne APENAS JSON.

Texto: "{mensagem}"

Formato:
{{
  "valor": number,
  "categoria": string,
  "descricao": string
}}
""",
        response_format={"type": "json_object"}
    )

    return response.output_parsed



# =====================
# TELEGRAM - ENVIAR MENSAGEM
# =====================

def enviar_mensagem(chat_id, texto):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto
    }
    requests.post(url, json=payload)

# =====================
# WEBHOOK TELEGRAM
# =====================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if "message" not in data:
        return jsonify({"status": "ignored"})

    chat_id = data["message"]["chat"]["id"]
    mensagem = data["message"].get("text", "")
    texto = mensagem.lower().strip()   # 👈 FIX AQUI


    if texto in ["relatorio", "relatório", "total", "/relatorio"]:
        total, categorias = obter_relatorio(chat_id)

        resposta = "📊 Relatório de Gastos\n\n"
        resposta += f"💰 Total: R$ {total:.2f}\n\n"

        for categoria, valor in categorias:
            resposta += f"- {categoria}: R$ {valor:.2f}\n"

        enviar_mensagem(chat_id, resposta)
        return jsonify({"status": "ok"})
    
    try:
        gasto = interpretar_gasto(mensagem)

        salvar_gasto(
            chat_id,
            gasto["valor"],
            gasto["categoria"],
            gasto["descricao"]
        )

        resposta = (
            f"✅ Gasto registrado!\n\n"
            f"💰 Valor: R$ {gasto['valor']}\n"
            f"📂 Categoria: {gasto['categoria']}\n"
            f"📝 Descrição: {gasto['descricao']}"
        )

    except Exception:
        resposta = (
            "❌ Não consegui entender.\n\n"
            "Exemplo:\n"
            "👉 gastei 35 reais com almoço"
        )

    enviar_mensagem(chat_id, resposta)
    return jsonify({"status": "ok"})


def obter_relatorio(chat_id):
    conn = conectar_db()
    cursor = conn.cursor()

    # total geral
    cursor.execute(
        "SELECT SUM(valor) FROM gastos WHERE chat_id = ?",
        (chat_id,)
    )
    total = cursor.fetchone()[0] or 0

    # total por categoria
    cursor.execute(
        """
        SELECT categoria, SUM(valor)
        FROM gastos
        WHERE chat_id = ?
        GROUP BY categoria
        """,
        (chat_id,)
    )
    categorias = cursor.fetchall()

    conn.close()
    return total, categorias



# =====================
# INICIALIZAÇÃO
# =====================

if __name__ == "__main__":
    criar_tabela()
    app.run(host="0.0.0.0", port=5000, debug=True)


