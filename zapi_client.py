import os
import requests
import logging

logger = logging.getLogger(__name__)

class ZAPIClient:
    """Cliente para integração com a Z-API WhatsApp."""

    def __init__(self):
        self.instance_id = os.getenv("ZAPI_INSTANCE_ID")
        self.token = os.getenv("ZAPI_TOKEN")
        self.client_token = os.getenv("ZAPI_CLIENT_TOKEN")  # Token adicional da Z-API
        self.base_url = "https://api.z-api.io"

        if not self.instance_id or not self.token:
            logger.critical("Credenciais da Z-API não configuradas! O envio de mensagens não funcionará. Verifique as variáveis de ambiente ZAPI_INSTANCE_ID e ZAPI_TOKEN.")

    def send_message(self, phone_number, message):
        """Envia uma mensagem de texto para um número de WhatsApp."""
        logger.info(f"🔄 Tentando enviar mensagem para {phone_number}")
        logger.info(f"📱 Número formatado: {phone_number}")
        logger.info(f"💬 Mensagem: {message[:100]}...")
        
        if not self.instance_id or not self.token:
            logger.error("❌ Credenciais Z-API ausentes!")
            logger.error(f"Instance ID presente: {bool(self.instance_id)}")
            logger.error(f"Token presente: {bool(self.token)}")
            logger.error(f"Client Token presente: {bool(self.client_token)}")
            return False

        # URL correta para Z-API - endpoint send-text
        url = f"{self.base_url}/instances/{self.instance_id}/token/{self.token}/send-text"
        
        # Headers necessários para Z-API
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Adicionar Client-Token se disponível nas variáveis de ambiente
        if self.client_token:
            headers['client-token'] = self.client_token  # Usar lowercase conforme documentação
            
        payload = {"phone": phone_number, "message": message}
        
        logger.info(f"🌐 URL da API: {url}")
        logger.info(f"📦 Payload: {payload}")
        logger.info(f"🔗 Headers: {headers}")

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            
            logger.info(f"📊 Status Code: {response.status_code}")
            logger.info(f"📄 Resposta da API: {response.text}")
            logger.info(f"🔗 Headers da resposta: {dict(response.headers)}")

            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"✅ Resposta JSON: {response_data}")
                
                # Verificar se há erro na resposta mesmo com status 200
                if response_data.get('error'):
                    logger.error(f"❌ Erro na resposta da Z-API: {response_data}")
                    return False
                    
                logger.info(f"✅ Mensagem enviada com sucesso para {phone_number}")
                return True
            else:
                logger.error(f"❌ Falha ao enviar mensagem para {phone_number}")
                logger.error(f"Status: {response.status_code}")
                logger.error(f"Resposta: {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de rede ao enviar mensagem para {phone_number}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao enviar mensagem: {e}")
            return False