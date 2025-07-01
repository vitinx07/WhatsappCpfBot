import re
import logging

logger = logging.getLogger(__name__)

class CPFValidator:
    """Classe para validar e formatar números de CPF."""

    def clean_cpf(self, cpf):
        """Remove qualquer caractere não numérico do CPF."""
        if not cpf or not isinstance(cpf, str):
            return ""
        return re.sub(r'\D', '', cpf)

    def is_valid_cpf(self, cpf):
        """Verifica a validade completa de um CPF (formato e dígitos verificadores)."""
        cpf_clean = self.clean_cpf(cpf)

        # Verifica se tem 11 dígitos e se não são todos iguais
        if len(cpf_clean) != 11 or len(set(cpf_clean)) == 1:
            return False

        try:
            # Cálculo do primeiro dígito verificador
            sum1 = sum(int(cpf_clean[i]) * (10 - i) for i in range(9))
            check_digit1 = (sum1 * 10) % 11
            if check_digit1 == 10: check_digit1 = 0

            # Cálculo do segundo dígito verificador
            sum2 = sum(int(cpf_clean[i]) * (11 - i) for i in range(10))
            check_digit2 = (sum2 * 10) % 11
            if check_digit2 == 10: check_digit2 = 0

            # Compara com os dígitos do CPF
            return check_digit1 == int(cpf_clean[9]) and check_digit2 == int(cpf_clean[10])
        except (ValueError, IndexError):
            return False

    def format_cpf(self, cpf):
        """Formata um CPF limpo com a máscara XXX.XXX.XXX-XX."""
        cpf_clean = self.clean_cpf(cpf)
        if len(cpf_clean) == 11:
            return f"{cpf_clean[:3]}.{cpf_clean[3:6]}.{cpf_clean[6:9]}-{cpf_clean[9:]}"
        return cpf_clean