# app.py

import os
import logging
from flask import Flask, request, jsonify, render_template, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import json

# Importa o 'db' do novo arquivo
from extensions import db

# --- Configuração do Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Criação e Configuração da Aplicação Flask ---
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "uma-chave-secreta-forte-e-dificil-de-adivinhar")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///whatsapp_bot.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Inicializa o banco de dados com a aplicação
db.init_app(app)

# --- Importação dos Componentes do Projeto ---
# Agora podemos importar tudo sem medo de ciclos
from models import Message, Conversation
from cpf_validator import CPFValidator
from zapi_client import ZAPIClient
from conversation_manager import ConversationManager

# --- Inicialização dos Serviços ---
cpf_validator = CPFValidator()
zapi_client = ZAPIClient()
conversation_manager = ConversationManager(db)

# Cria as tabelas do banco de dados
with app.app_context():
    db.create_all()

# --- Rotas da Aplicação ---

@app.route("/")
def admin_dashboard():
    # ... (o conteúdo desta função permanece o mesmo) ...
    try:
        stats = {
            'total_conversations': db.session.query(Conversation).count(),
            'active_conversations': db.session.query(Conversation).filter_by(status='active').count(),
            'total_messages': db.session.query(Message).count(),
            'recent_messages': db.session.query(Message).order_by(Message.timestamp.desc()).limit(10).all()
        }
        return render_template('admin.html', stats=stats)
    except Exception as e:
        logger.error(f"Erro ao carregar o dashboard: {str(e)}")
        flash(f"Não foi possível carregar os dados do dashboard: {str(e)}", 'error')
        return render_template('admin.html', stats={})


@app.route("/logs")
def view_logs():
    # ... (o conteúdo desta função permanece o mesmo) ...
    try:
        conversations = db.session.query(Conversation).order_by(Conversation.last_activity.desc()).limit(50).all()
        return render_template('logs.html', conversations=conversations)
    except Exception as e:
        logger.error(f"Erro ao carregar os logs: {str(e)}")
        flash(f"Não foi possível carregar os logs de conversas: {str(e)}", 'error')
        return render_template('logs.html', conversations=[])


@app.route("/webhook", methods=["POST"])
def webhook():
    # ... (o conteúdo desta função permanece o mesmo) ...
    try:
        data = request.json
        logger.debug(f"Webhook recebido: {json.dumps(data, indent=2)}")
        texto = data.get("text", {}).get("message", "").strip()
        numero = data.get("phone", "")
        if data.get("fromMe", False) or not numero or not texto:
            return jsonify({"status": "ignored"}), 200
        logger.info(f"Processando mensagem de {numero}: '{texto}'")
        incoming_message = Message(phone_number=numero, message_body=texto, message_type='incoming')
        db.session.add(incoming_message)
        resposta = conversation_manager.process_message(numero, texto)
        if resposta:
            success = zapi_client.send_message(numero, resposta)
            if success:
                outgoing_message = Message(phone_number=numero, message_body=resposta, message_type='outgoing')
                db.session.add(outgoing_message)
                logger.info(f"Resposta enviada para {numero}: '{resposta}'")
            else:
                logger.error(f"Falha ao enviar resposta para {numero}")
        db.session.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Erro crítico no webhook: {str(e)}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/test-cpf", methods=["POST"])
def test_cpf():
    # ... (o conteúdo desta função permanece o mesmo) ...
    try:
        cpf = request.json.get('cpf', '')
        is_valid = cpf_validator.is_valid_cpf(cpf)
        message = "CPF válido." if is_valid else "CPF inválido."
        return jsonify({"valid": is_valid, "message": message})
    except Exception as e:
        logger.error(f"Erro no teste de CPF: {str(e)}")
        return jsonify({"valid": False, "message": "Erro ao processar a requisição."}), 500


@app.route("/health")
def health_check():
    # ... (o conteúdo desta função permanece o mesmo) ...
    try:
        db.session.execute(db.select(1))
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected: {e}"
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint não encontrado"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erro interno do servidor: {str(error)}")
    return jsonify({"error": "Ocorreu um erro interno no servidor"}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)