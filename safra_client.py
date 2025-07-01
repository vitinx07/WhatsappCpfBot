
import requests
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SafraAPIClient:
    """Cliente completo para simular o refinanciamento de contratos na API do Safra."""

    def __init__(self, username, password):
        self.base_url = "https://api.safrafinanceira.com.br/apl-api-correspondente/api/v1"
        self.username = username
        self.password = password
        self.token = None
        logger.info("SafraAPIClient inicializado.")

    def _make_request(self, method, endpoint, **kwargs):
        """Método centralizado para fazer requisições HTTP e tratar erros."""
        url = f"{self.base_url}/{endpoint}"
        headers = kwargs.pop('headers', {})
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            response = requests.request(method, url, headers=headers, timeout=45, **kwargs)
            if response.status_code in [401, 403]: 
                return {"error": "auth", "message": "Token da API Safra inválido ou expirado."}
            if response.status_code >= 500: 
                return {"error": "server", "message": "O servidor da API Safra encontrou um erro interno."}
            if not response.content: 
                return {}
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de rede na requisição Safra: {e}")
            return {"error": "network", "details": str(e)}

    def autenticar(self):
        """Autentica na API e armazena o token."""
        logger.info("Autenticando no Safra...")
        payload = {"username": self.username, "password": self.password}
        headers = {'Content-Type': 'application/json'}
        response = self._make_request("POST", "Token", json=payload, headers=headers)
        
        if isinstance(response, dict) and not response.get("error"):
            self.token = response.get("accessToken") or response.get("token")
            if self.token:
                logger.info("Autenticação Safra bem-sucedida.")
                return True
        logger.error("Falha na autenticação Safra.")
        return False

    def consultar_dados_cadastrais(self, cpf):
        """Busca dados cadastrais (sexo, nascimento) pelo CPF."""
        if not self.token: 
            return None
        logger.info(f"Buscando dados cadastrais para CPF {cpf}...")
        endpoint = f"ContratosDadosCadastrais/cpf/{cpf}"
        response = self._make_request("GET", endpoint)

        if response and isinstance(response, list) and len(response) > 0:
            dados = response[0]
            sexo_str = dados.get("dsSexoCliente")
            nascimento_str = dados.get("dtNascimentoCliente")
            if sexo_str and nascimento_str:
                sexo = sexo_str[0].upper()
                logger.info("Dados cadastrais encontrados automaticamente.")
                return {"idSexo": sexo, "dtNascimento": nascimento_str}
        
        logger.warning("Não foi possível buscar dados cadastrais automaticamente.")
        return None

    def descobrir_id_convenio(self, nome_convenio="INSS"):
        """Busca o ID do convênio 'INSS'."""
        if not self.token: 
            return None
        logger.info(f"Buscando ID para convênio '{nome_convenio}'...")
        params = {'nome': nome_convenio}
        response = self._make_request("GET", "Convenio", params=params)

        if isinstance(response, list) and len(response) > 0:
            for convenio in response:
                if convenio.get("nome", "").upper() == nome_convenio.upper():
                    id_encontrado = convenio.get("idConvenio")
                    logger.info(f"ID do Convênio encontrado: {id_encontrado}")
                    return id_encontrado
        logger.error(f"Não foi possível encontrar o convênio '{nome_convenio}'.")
        return None

    def consultar_contratos_refin(self, cpf, id_convenio):
        """Busca os contratos do cliente que estão disponíveis para refinanciamento."""
        if not self.token: 
            return None
        logger.info("Consultando contratos elegíveis para refinanciamento...")
        endpoint = f"Contratos/{cpf}/{id_convenio}/Refin"
        response = self._make_request("GET", endpoint)
        if response is not None and not (isinstance(response, dict) and response.get("error")):
            logger.info(f"Consulta bem-sucedida. {len(response)} contrato(s) encontrado(s).")
            return response
        return None

    def simular_refinanciamento(self, dados_completos, contrato_a_simular):
        """Executa a simulação de refinanciamento para um único contrato."""
        if not self.token: 
            return None
        
        matricula_do_contrato = contrato_a_simular.get("matricula")
        logger.info(f"Executando simulação para Contrato ID: {contrato_a_simular.get('idContrato')}")
        
        endpoint = "Calculo/Refin"
        headers = {'Content-Type': 'application/json'}
        
        payload = {
            "idConvenio": dados_completos["id_convenio"], 
            "cpf": dados_completos["cpf"],
            "matricula": matricula_do_contrato,
            "isCotacao": True,
            "refins": [{"idContrato": contrato_a_simular.get("idContrato")}],
            "dtNascimento": dados_completos["dtNascimento"], 
            "idSexo": dados_completos["idSexo"],
            "idSituacaoEmpregado": dados_completos["idSituacaoEmpregado"]
        }
        return self._make_request("POST", endpoint, json=payload, headers=headers)
