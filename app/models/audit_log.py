from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.core.database import Base # Ajuste este import para o Base do banco

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_hash = Column(String(255), nullable=False, index=True) # Guardamos apenas um hash, não o ID real
    action = Column(String(50), nullable=False) # Ex: "account_deletion"
    created_at = Column(DateTime, server_default=func.now(), nullable=False)