from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# Use environment variables for credentials
ZAPI_INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID", "3E377668BA5050E7B1EB82E7EA6BFAB8")
ZAPI_TOKEN = os.getenv("ZAPI_TOKEN", "6F5BF721D4D89171C1C16E35")

def enviar_resposta(numero, mensagem):
    url = f"https://api.z-api.io/instances/{ZAPI_INSTANCE_ID}/token/{ZAPI_TOKEN}/send-message"
    payload = {
        "phone": numero,
        "message": mensagem
    }
    try:
        response = requests.post(url, json=payload)
        print(f"Mensagem enviada para {numero}: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
        return False

@app.route("/", methods=["POST"])
def webhook():
    data = request.json
    print(f"Dados recebidos: {data}")

    try:
        # Verifica se a estrutura JSON contém as chaves necessárias
        if not data or "message" not in data:
            print("Dados inválidos: estrutura de mensagem ausente")
            return jsonify({"status": "erro", "mensagem": "Dados inválidos"}), 400
        
        message_data = data["message"]
        
        if "body" not in message_data or "from" not in message_data:
            print("Campos obrigatórios ausentes na mensagem")
            return jsonify({"status": "erro", "mensagem": "Campos obrigatórios ausentes"}), 400
        
        texto = message_data["body"]
        numero_completo = message_data["from"]
        numero = numero_completo.split("@")[0]   

        # Lógica de resposta
        if texto.lower() in ["oi", "olá", "bom dia", "boa tarde"]:
            resposta = "Olá! 👋 Sou seu assistente de consignado. Por favor, envie seu CPF (apenas números)."
        elif texto.isdigit() and len(texto) == 11:
            resposta = f"CPF {texto} recebido com sucesso! 🔎 Agora irei consultar suas oportunidades nos bancos disponíveis..."
        else:
            resposta = "Desculpe, não entendi. Envie apenas o número do seu CPF (11 dígitos) para continuar."

        # Enviar resposta
        sucesso = enviar_resposta(numero, resposta)
        
        if sucesso:
            return jsonify({"status": "ok", "mensagem": resposta})
        else:
            return jsonify({"status": "erro", "mensagem": "Falha ao enviar mensagem"}), 500

    except Exception as e:
        print(f"Erro no webhook: {e}")
        return jsonify({"erro": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "WhatsApp Bot Consignado"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)