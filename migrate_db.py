
import os
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Migra o banco de dados para adicionar a coluna extra_data."""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        logger.error("DATABASE_URL não encontrada nas variáveis de ambiente")
        return False
    
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Verifica se a coluna extra_data já existe
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='conversations' AND column_name='extra_data';
        """)
        
        if cur.fetchone():
            logger.info("Coluna extra_data já existe na tabela conversations")
            return True
        
        # Adiciona a coluna extra_data
        logger.info("Adicionando coluna extra_data à tabela conversations...")
        cur.execute("ALTER TABLE conversations ADD COLUMN extra_data JSON;")
        
        conn.commit()
        logger.info("✅ Migração concluída com sucesso!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro na migração: {e}")
        return False
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    migrate_database()
