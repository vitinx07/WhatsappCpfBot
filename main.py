
from flask import Flask, request, jsonify, render_template
import os
import logging
from datetime import datetime
from werkzeug.middleware.proxy_fix import ProxyFix

# Importa as classes de outros arquivos do projeto
from extensions import db
from models import Message, Conversation
from zapi_client import ZAPIClient
from cpf_validator import CPFValidator
from safra_client import SafraAPIClient

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "uma-chave-secreta-forte")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configuração do banco de dados
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///whatsapp_bot.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Inicializa o banco de dados
db.init_app(app)

# --- INICIALIZAÇÃO DOS SERVIÇOS ---
zapi_client = ZAPIClient()
cpf_validator = CPFValidator()
safra_client = SafraAPIClient(
    username=os.getenv("SAFRA_USERNAME", "SEU_USUARIO_SAFRA"),
    password=os.getenv("SAFRA_PASSWORD", "SUA_SENHA_SAFRA")
)

# Cria as tabelas do banco de dados e executa migrações
with app.app_context():
    db.create_all()
    
    # Migração automática para adicionar coluna extra_data se não existir
    try:
        from sqlalchemy import text
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='conversations' AND column_name='extra_data';
        """))
        
        if not result.fetchone():
            logger.info("Executando migração: adicionando coluna extra_data...")
            db.session.execute(text("ALTER TABLE conversations ADD COLUMN extra_data JSON;"))
            db.session.commit()
            logger.info("✅ Migração concluída!")
        
    except Exception as e:
        logger.info(f"Migração automática não necessária ou falhou: {e}")
        db.session.rollback()


class ConversationManager:
    """Gerencia o fluxo e estado da conversa."""

    def __init__(self, db_instance):
        self.db = db_instance

    def process_message(self, phone_number, message_text):
        """Processa uma mensagem recebida e retorna a resposta apropriada."""
        conversation = self._get_or_create_conversation(phone_number)
        conversation.update_activity()

        response = self._generate_response(conversation, message_text)
        self.db.session.commit()
        return response

    def _get_or_create_conversation(self, phone_number):
        """Busca uma conversa existente no banco ou cria uma nova."""
        conversation = self.db.session.query(Conversation).filter_by(
            phone_number=phone_number).first()
        if not conversation:
            conversation = Conversation(phone_number=phone_number, status='waiting_cpf')
            self.db.session.add(conversation)
            self.db.session.commit()
            logger.info(f"Nova conversa criada para {phone_number}")
        return conversation

    def _generate_response(self, conversation, message_text):
        """Decide qual resposta enviar com base no estado da conversa."""
        command = message_text.lower().strip()

        if command in ['ajuda', 'help', 'menu']:
            return self._get_help_response()
        if command in ['reiniciar', 'começar', 'start', 'oi', 'olá', 'ola']:
            return self._start_new_conversation(conversation)

        if conversation.status == 'waiting_cpf':
            return self._handle_cpf_input(conversation, message_text)
        if conversation.status == 'waiting_nascimento':
            return self._handle_nascimento_input(conversation, message_text)
        if conversation.status == 'waiting_sexo':
            return self._handle_sexo_input(conversation, message_text)
        if conversation.status == 'waiting_situacao':
            return self._handle_situacao_input(conversation, message_text)

        # Se não corresponder a nenhum estado, reinicia a conversa
        return self._start_new_conversation(conversation)

    def _start_new_conversation(self, conversation):
        """Inicia ou reinicia o fluxo, pedindo o CPF."""
        conversation.status = 'waiting_cpf'
        conversation.cpf = None
        return ("👋 Olá! Sou seu assistente de consignado do Safra.\n\n"
                "Para começar, por favor, envie seu CPF (apenas números).")

    def _handle_cpf_input(self, conversation, cpf_text):
        """Valida o CPF e avança para a data de nascimento."""
        cpf_clean = cpf_validator.clean_cpf(cpf_text)
        if not cpf_validator.is_valid_cpf(cpf_clean):
            return "❌ CPF inválido. Por favor, verifique os 11 dígitos e tente novamente."

        conversation.cpf = cpf_clean
        conversation.status = 'waiting_nascimento'

        return (
            f"✅ CPF {cpf_validator.format_cpf(cpf_clean)} recebido!\n\n"
            "📅 Agora, por favor, informe sua data de nascimento no formato DD/MM/AAAA.\n\n"
            "Exemplo: 15/03/1985")

    def _handle_nascimento_input(self, conversation, nascimento_text):
        """Valida a data de nascimento e avança para o sexo."""
        try:
            # Valida o formato da data
            datetime_obj = datetime.strptime(nascimento_text.strip(), '%d/%m/%Y')
            dt_iso_str = datetime_obj.strftime('%Y-%m-%d')
            dt_nascimento = f"{dt_iso_str}T00:00:00"
            
            # Salva os dados na conversa (usando um campo genérico para dados extras)
            if not hasattr(conversation, 'extra_data') or conversation.extra_data is None:
                conversation.extra_data = {}
            else:
                conversation.extra_data = conversation.extra_data or {}
            
            conversation.extra_data['dtNascimento'] = dt_nascimento
            conversation.status = 'waiting_sexo'
            
            return (
                f"✅ Data de nascimento {nascimento_text} recebida!\n\n"
                "👤 Agora, por favor, informe seu sexo:\n\n"
                "🔹 Digite *M* para Masculino\n"
                "🔹 Digite *F* para Feminino")
                
        except ValueError:
            return "❌ Formato de data inválido. Por favor, use o formato DD/MM/AAAA.\n\nExemplo: 15/03/1985"

    def _handle_sexo_input(self, conversation, sexo_text):
        """Valida o sexo e avança para a situação do benefício."""
        sexo = sexo_text.strip().upper()
        if sexo not in ['M', 'F']:
            return "❌ Opção inválida. Por favor, digite *M* para Masculino ou *F* para Feminino."
        
        # Salva o sexo nos dados extras
        if not hasattr(conversation, 'extra_data') or conversation.extra_data is None:
            conversation.extra_data = {}
        conversation.extra_data['idSexo'] = sexo
        conversation.status = 'waiting_situacao'
        
        sexo_desc = "Masculino" if sexo == 'M' else "Feminino"
        return (
            f"✅ Sexo {sexo_desc} recebido!\n\n"
            "💼 Por fim, informe a situação do seu benefício:\n\n"
            "1️⃣ - Ativo\n"
            "2️⃣ - Inativo/Aposentado\n"
            "3️⃣ - Pensionista")

    def _handle_situacao_input(self, conversation, situacao_text):
        """Recebe a situação do benefício e inicia a simulação."""
        if situacao_text.strip() not in ['1', '2', '3']:
            return "❌ Opção inválida. Por favor, digite 1, 2 ou 3 para a situação do benefício."

        # Salva a situação nos dados extras
        if not hasattr(conversation, 'extra_data') or conversation.extra_data is None:
            conversation.extra_data = {}
        conversation.extra_data['idSituacaoEmpregado'] = int(situacao_text)
        
        # Marca como processando
        conversation.status = 'processing'
        
        # Executa a simulação com todos os dados coletados
        resultados_finais = self._run_full_safra_simulation(conversation)

        # Marca como finalizada
        conversation.status = 'completed'
        return resultados_finais

    def _run_full_safra_simulation(self, conversation):
        """Orquestra as chamadas à API Safra e formata o resultado."""
        cpf = conversation.cpf
        extra_data = conversation.extra_data or {}
        
        logger.info(f"Iniciando simulação completa para CPF: {cpf}")
        
        # Tenta autenticar na API Safra
        if not safra_client.autenticar():
            logger.warning("Falha na autenticação - usando modo simulação")
            return self._simulate_safra_response(cpf)

        # Busca dados cadastrais automaticamente, se disponível
        dados_cadastrais = safra_client.consultar_dados_cadastrais(cpf)
        if not dados_cadastrais:
            # Usa os dados coletados manualmente
            dados_cadastrais = {
                "dtNascimento": extra_data.get('dtNascimento'),
                "idSexo": extra_data.get('idSexo')
            }
            logger.info("Usando dados coletados manualmente do usuário")
        else:
            logger.info("Usando dados cadastrais da API")

        id_convenio = safra_client.descobrir_id_convenio("INSS")
        if not id_convenio:
            logger.warning("Convênio não encontrado - usando modo simulação")
            return self._simulate_safra_response(cpf)

        contratos = safra_client.consultar_contratos_refin(cpf, id_convenio)
        if not contratos:
            return self._format_no_contracts_response(cpf)

        # Prepara dados completos para simulação
        dados_simulacao = {
            "cpf": int(cpf),
            "id_convenio": id_convenio,
            "idSituacaoEmpregado": extra_data.get('idSituacaoEmpregado'),
            "dtNascimento": dados_cadastrais.get("dtNascimento"),
            "idSexo": dados_cadastrais.get("idSexo")
        }

        resultados_finais = []
        for contrato in contratos:
            simulacao = safra_client.simular_refinanciamento(dados_simulacao, contrato)
            resultados_finais.append({
                "contrato_id": contrato.get("idContrato"),
                "parcela_original": contrato.get("valorParcela"),
                "simulacao": simulacao
            })

        return self._format_results_response(cpf, resultados_finais)

    def _simulate_safra_response(self, cpf):
        """Simula uma resposta da API Safra para desenvolvimento."""
        cpf_formatado = cpf_validator.format_cpf(cpf)
        
        return (
            f"✅ Consulta para o CPF {cpf_formatado} finalizada!\n\n"
            "🔍 *Modo Simulação Ativo*\n\n"
            "Encontramos as seguintes oportunidades de refinanciamento:\n\n"
            "📄 *Contrato ID: 12345*\n"
            "   *Parcela Atual:* R$ 450,00\n"
            "   *Opções de Troco Liberado:*\n"
            "     - Em *24 meses* ➡ *Troco de R$ 2.500,00*\n"
            "     - Em *36 meses* ➡ *Troco de R$ 3.200,00*\n"
            "     - Em *48 meses* ➡ *Troco de R$ 4.100,00*\n\n"
            "📄 *Contrato ID: 67890*\n"
            "   *Parcela Atual:* R$ 320,00\n"
            "   *Opções de Troco Liberado:*\n"
            "     - Em *30 meses* ➡ *Troco de R$ 1.800,00*\n"
            "     - Em *42 meses* ➡ *Troco de R$ 2.400,00*\n\n"
            "💡 *Importante:* Estes são valores simulados para demonstração.\n\n"
            "Digite *oi* para iniciar uma nova consulta."
        )

    def _format_no_contracts_response(self, cpf):
        """Formata resposta quando não há contratos."""
        cpf_formatado = cpf_validator.format_cpf(cpf)
        return (
            f"✅ Consulta para o CPF {cpf_formatado} finalizada.\n\n"
            "Nenhuma oportunidade de refinanciamento foi encontrada no momento.\n\n"
            "Digite *oi* para iniciar uma nova consulta."
        )

    def _format_results_response(self, cpf, resultados):
        """Formata os resultados da simulação."""
        cpf_formatado = cpf_validator.format_cpf(cpf)
        
        mensagem = [
            f"✅ Consulta para o CPF {cpf_formatado} finalizada!\n\n"
            "Encontramos as seguintes oportunidades de refinanciamento:\n"
        ]

        for resultado in resultados:
            contrato_id = resultado["contrato_id"]
            parcela_original = resultado["parcela_original"]
            simulacao = resultado["simulacao"]

            bloco_texto = f"\n📄 *Contrato ID: {contrato_id}*\n"
            bloco_texto += f"   *Parcela Atual:* R$ {parcela_original:.2f}\n"

            if simulacao and simulacao.get("simulacoes"):
                bloco_texto += "   *Opções de Troco Liberado:*\n"
                for sim in simulacao["simulacoes"]:
                    bloco_texto += f"     - Em *{sim.get('prazo')} meses* ➡ *Troco de R$ {sim.get('valorTroco'):.2f}*\n"
            elif simulacao and simulacao.get("criticas"):
                bloco_texto += f"   *Status:* Não elegível\n"
                bloco_texto += f"   *Motivo:* {simulacao['criticas'][0]}\n"
            else:
                bloco_texto += "   *Status:* Não foi possível simular este contrato.\n"

            mensagem.append(bloco_texto)

        mensagem.append("\nDigite *oi* para iniciar uma nova consulta.")
        return "".join(mensagem)

    def _get_help_response(self):
        """Retorna a mensagem de ajuda padrão."""
        return ("📖 *Como usar o assistente:*\n\n"
                "1️⃣ Digite seu *CPF* (apenas números)\n"
                "2️⃣ Informe sua *data de nascimento* (DD/MM/AAAA)\n"
                "3️⃣ Informe seu *sexo* (M ou F)\n"
                "4️⃣ Escolha a *situação do benefício* (1, 2 ou 3)\n\n"
                "• Digite *oi* para iniciar uma nova consulta\n"
                "• Digite *ajuda* para ver esta mensagem")


# Inicializar o gerenciador de conversas
conversation_manager = ConversationManager(db)


@app.route("/webhook", methods=["POST"])
def webhook():
    """Recebe e processa as mensagens do WhatsApp."""
    try:
        data = request.json or {}
        texto = data.get("text", {}).get("message", "").strip()
        numero = data.get("phone", "")

        # Ignora mensagens próprias ou inválidas
        if data.get("fromMe", False) or not numero or not texto:
            return jsonify({"status": "ignored"})

        logger.info(f"Mensagem recebida de {numero}: {texto}")

        # Salva a mensagem recebida
        incoming_message = Message(
            phone_number=numero, 
            message_body=texto, 
            message_type='incoming'
        )
        db.session.add(incoming_message)

        # Processa a mensagem e gera resposta
        resposta = conversation_manager.process_message(numero, texto)

        # Envia resposta se necessário
        if resposta:
            # Para situação especial de processamento, envia mensagem de espera primeiro
            conversation = db.session.query(Conversation).filter_by(phone_number=numero).first()
            if conversation and conversation.status == 'processing':
                mensagem_espera = "🔍 Perfeito! Iniciando a consulta completa... Isso pode levar alguns segundos."
                zapi_client.send_message(numero, mensagem_espera)
                
                # Salva mensagem de espera
                wait_message = Message(
                    phone_number=numero,
                    message_body=mensagem_espera,
                    message_type='outgoing'
                )
                db.session.add(wait_message)

            # Envia a resposta principal
            success = zapi_client.send_message(numero, resposta)
            
            if success:
                # Salva a resposta enviada
                outgoing_message = Message(
                    phone_number=numero,
                    message_body=resposta,
                    message_type='outgoing'
                )
                db.session.add(outgoing_message)
                logger.info(f"Resposta enviada para {numero}")
            else:
                logger.error(f"Falha ao enviar resposta para {numero}")

        db.session.commit()
        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Erro no webhook: {str(e)}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/", methods=["POST"])
def webhook_root():
    """Webhook alternativo na rota raiz."""
    return webhook()

@app.route("/", methods=["GET"])
def admin_dashboard():
    """Dashboard administrativo."""
    try:
        stats = {
            'total_conversations': db.session.query(Conversation).count(),
            'active_conversations': db.session.query(Conversation).filter(
                Conversation.status.in_(['waiting_cpf', 'waiting_situacao', 'processing'])
            ).count(),
            'total_messages': db.session.query(Message).count(),
            'recent_messages': db.session.query(Message).order_by(
                Message.timestamp.desc()
            ).limit(10).all()
        }
        return render_template('admin.html', stats=stats)
    except Exception as e:
        logger.error(f"Erro ao carregar dashboard: {str(e)}")
        return f"<h1>Bot WhatsApp Safra</h1><p>Erro: {str(e)}</p>", 500


@app.route("/logs")
def view_logs():
    """Visualização de logs."""
    try:
        conversations = db.session.query(Conversation).order_by(
            Conversation.last_activity.desc()
        ).limit(50).all()
        return render_template('logs.html', conversations=conversations)
    except Exception as e:
        logger.error(f"Erro ao carregar logs: {str(e)}")
        return f"<h1>Logs</h1><p>Erro: {str(e)}</p>", 500


@app.route("/health")
def health_check():
    """Verificação de saúde do sistema."""
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected: {str(e)}"
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "zapi_configured": bool(os.getenv("ZAPI_INSTANCE_ID") and os.getenv("ZAPI_TOKEN")),
        "safra_configured": bool(os.getenv("SAFRA_USERNAME") and os.getenv("SAFRA_PASSWORD"))
    })


@app.route("/test-cpf", methods=["POST"])
def test_cpf():
    """Teste de validação de CPF."""
    try:
        cpf = request.json.get('cpf', '')
        is_valid = cpf_validator.is_valid_cpf(cpf)
        message = "CPF válido." if is_valid else "CPF inválido."
        return jsonify({"valid": is_valid, "message": message})
    except Exception as e:
        logger.error(f"Erro no teste de CPF: {str(e)}")
        return jsonify({"valid": False, "message": "Erro ao processar."}), 500


@app.route("/test-zapi", methods=["POST"])
def test_zapi():
    """Teste das credenciais Z-API."""
    try:
        phone = request.json.get('phone', '5518996320169')
        message = request.json.get('message', '🧪 Teste de conectividade Z-API')
        
        logger.info(f"🧪 Iniciando teste Z-API para {phone}")
        success = zapi_client.send_message(phone, message)
        
        return jsonify({
            "success": success,
            "phone": phone,
            "message": message,
            "instance_configured": bool(os.getenv("ZAPI_INSTANCE_ID")),
            "token_configured": bool(os.getenv("ZAPI_TOKEN"))
        })
    except Exception as e:
        logger.error(f"Erro no teste Z-API: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint não encontrado"}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erro interno: {str(error)}")
    return jsonify({"error": "Erro interno do servidor"}), 500


if __name__ == "__main__":
    logger.info("Iniciando Bot WhatsApp Safra...")
    app.run(host="0.0.0.0", port=5000, debug=True)
