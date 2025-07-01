# models.py

# Importa o 'db' do novo arquivo, não mais do 'app'
from extensions import db
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean

class Message(db.Model):
    # ... (o conteúdo desta classe permanece o mesmo) ...
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    phone_number = Column(String(20), nullable=False, index=True)
    message_body = Column(Text, nullable=False)
    message_type = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


class Conversation(db.Model):
    """Modelo para armazenar conversas do WhatsApp."""

    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    status = db.Column(db.String(50), default='waiting_cpf')
    cpf = db.Column(db.String(11), nullable=True)
    extra_data = db.Column(db.JSON, nullable=True)  # Para armazenar data nascimento, sexo, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Conversation {self.phone_number} - {self.status}>'

    def update_activity(self):
        """Atualiza o timestamp da última atividade."""
        self.last_activity = datetime.utcnow()