import logging
import os
from models import Conversation
from cpf_validator import CPFValidator
from safra_client import SafraAPIClient

logger = logging.getLogger(__name__)


class ConversationManager:
    """Gerencia o fluxo e estado da conversa, integrando com a API Safra."""

    def __init__(self, db):
        self.db = db
        self.cpf_validator = CPFValidator()
        self.safra_client = SafraAPIClient(
            username=os.getenv("SAFRA_USERNAME", "SEU_USUARIO_SAFRA"),
            password=os.getenv("SAFRA_PASSWORD", "SUA_SENHA_SAFRA"))

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
            conversation = Conversation(phone_number=phone_number,
                                        status='active')
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
        if conversation.status == 'waiting_situacao':
            return self._handle_situacao_input(conversation, message_text)

        # Se não corresponder a nenhum estado, reinicia a conversa
        return self._start_new_conversation(conversation)

    def _start_new_conversation(self, conversation):
        """Inicia ou reinicia o fluxo, pedindo o CPF."""
        conversation.status = 'waiting_cpf'
        conversation.cpf = None
        return ("👋 Olá! Bem-vindo ao assistente de simulação Safra.\n\n"
                "Para começarmos, por favor, envie seu CPF (apenas números).")

    def _handle_cpf_input(self, conversation, cpf_text):
        """Valida o CPF e avança para o próximo passo."""
        cpf_clean = self.cpf_validator.clean_cpf(cpf_text)
        if not self.cpf_validator.is_valid_cpf(cpf_clean):
            return "❌ CPF inválido. Por favor, verifique os 11 dígitos e tente novamente."

        conversation.cpf = cpf_clean
        conversation.status = 'waiting_situacao'

        return (
            f"✅ CPF {self.cpf_validator.format_cpf(cpf_clean)} recebido!\n\n"
            "Agora, por favor, informe a situação do seu benefício:\n"
            "1️⃣ - Ativo\n"
            "2️⃣ - Inativo/Aposentado\n"
            "3️⃣ - Pensionista")

    def _handle_situacao_input(self, conversation, situacao_text):
        """Recebe a situação do benefício e inicia a simulação."""
        if situacao_text.strip() not in ['1', '2', '3']:
            return "Opção inválida. Por favor, digite 1, 2 ou 3 para a situação do benefício."

        # Retorna uma mensagem de espera enquanto a consulta é feita
        # A resposta final será enviada de forma assíncrona na implementação real,
        # mas aqui retornamos o resultado direto.

        resultados_finais = self._run_full_safra_simulation(
            conversation.cpf, int(situacao_text))

        conversation.status = 'completed'  # Finaliza o fluxo principal
        return resultados_finais

    def _run_full_safra_simulation(self, cpf, id_situacao):
        """Orquestra as chamadas à API Safra e formata o resultado."""
        if not self.safra_client.autenticar():
            return "Desculpe, não foi possível conectar ao sistema do banco no momento. Tente novamente mais tarde."

        dados_cadastrais = self.safra_client.consultar_dados_cadastrais(cpf)
        if not dados_cadastrais:
            return "Não foi possível encontrar seus dados cadastrais. Verifique o CPF ou tente novamente."

        id_convenio = self.safra_client.descobrir_id_convenio("INSS")
        if not id_convenio:
            return "Não foi possível encontrar o convênio INSS no sistema."

        contratos = self.safra_client.consultar_contratos_refin(
            cpf, id_convenio)
        if not contratos:
            return "✅ Consulta finalizada. Não foram encontrados contratos abertos para refinanciamento para este CPF."

        dados_simulacao = {
            "cpf": int(cpf),
            "id_convenio": id_convenio,
            "idSituacaoEmpregado": id_situacao,
            **dados_cadastrais
        }

        final_response = [
            f"✅ Consulta finalizada! Encontramos {len(contratos)} oportunidade(s) de refinanciamento:\n"
        ]

        for contrato in contratos:
            simulacao = self.safra_client.simular_refinanciamento(
                dados_simulacao, contrato)
            bloco_texto = self._formatar_bloco_simulacao(contrato, simulacao)
            final_response.append(bloco_texto)

        final_response.append("\nDigite 'oi' para iniciar uma nova consulta.")
        return "".join(final_response)

    def _formatar_bloco_simulacao(self, contrato, simulacao):
        """Formata o bloco de texto para um único contrato simulado."""
        contrato_id = contrato.get('idContrato', 'N/A')
        parcela_valor = contrato.get('valorParcela', 0)

        bloco_texto = f"\n📄 *Contrato ID: {contrato_id}*\n"
        bloco_texto += f"   *Parcela Original:* R$ {parcela_valor:.2f}\n"

        if simulacao and simulacao.get("simulacoes"):
            bloco_texto += "   *Opções de Troco:*\n"
            for sim in simulacao["simulacoes"]:
                bloco_texto += f"     - *Prazo:* {sim.get('prazo')} meses -> *Troco:* R$ {sim.get('valorTroco'):.2f}\n"
        elif simulacao and simulacao.get("criticas"):
            bloco_texto += f"   *Status:* Não elegível\n   *Motivo:* {simulacao['criticas'][0]}\n"
        else:
            bloco_texto += "   *Status:* Não foi possível simular este contrato.\n"
        return bloco_texto

    def _get_help_response(self):
        """Retorna a mensagem de ajuda padrão."""
        return ("📖 *Comandos disponíveis:*\n\n"
                "• Envie seu *CPF* para iniciar uma consulta.\n"
                "• Digite *oi* ou *reiniciar* para começar uma nova busca.")
