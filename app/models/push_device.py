from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.utils import utc_now

from ..core.database import Base


class PushDevice(Base):
    """
    Aparelho que recebe push pelo Expo Push Service (#43). O token é do Expo
    (ExponentPushToken[...]); o Expo entrega via APNs e FCM. O PushSubscription
    antigo é de web push (endpoint e chaves do navegador) e não serve ao app.
    """

    __tablename__ = "push_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # um aparelho, um dono: logar com outra conta no mesmo celular transfere o token
    expo_push_token: Mapped[str] = mapped_column(String(200), unique=True)
    platform: Mapped[str] = mapped_column(String(20))  # ios | android
    app_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
