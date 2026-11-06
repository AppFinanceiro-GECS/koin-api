"""
Envio de push pelo Expo Push Service (#43). O Expo entrega via APNs (iOS) e FCM
(Android) com as credenciais configuradas no projeto EAS; a API só precisa do token
do aparelho. Grátis; EXPO_ACCESS_TOKEN é opcional (só se o projeto exigir).

https://docs.expo.dev/push-notifications/sending-notifications/
"""

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
# Limite do Expo por requisição
BATCH_SIZE = 100

_TOKEN = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{10,}\]$")


def is_expo_token(token: str) -> bool:
    return bool(_TOKEN.fullmatch(token or ""))


def build_message(token: str, title: str, body: str, data: dict | None = None) -> dict:
    return {
        "to": token,
        "title": title,
        "body": body,
        "data": data or {},
        "sound": "default",
        "priority": "high",
    }


async def send_push(messages: list[dict], client: httpx.AsyncClient | None = None) -> list[dict]:
    """Envia em lotes e devolve um ticket por mensagem, na mesma ordem.

    Ticket: {"status": "ok"} ou {"status": "error", "details": {"error": "DeviceNotRegistered"}}.
    Falha de rede vira ticket de erro com details.error = "NetworkError" (tenta no próximo ciclo).
    """
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if settings.expo_access_token:
        headers["Authorization"] = f"Bearer {settings.expo_access_token}"

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=15)
    tickets: list[dict] = []
    try:
        for start in range(0, len(messages), BATCH_SIZE):
            batch = messages[start : start + BATCH_SIZE]
            try:
                response = await client.post(EXPO_PUSH_URL, json=batch, headers=headers)
                response.raise_for_status()
                data = response.json().get("data", [])
                if len(data) != len(batch):
                    raise ValueError(f"expo devolveu {len(data)} tickets para {len(batch)}")
                tickets.extend(data)
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("push_send_failed error_type=%s", type(e).__name__)
                tickets.extend(
                    {"status": "error", "details": {"error": "NetworkError"}} for _ in batch
                )
    finally:
        if own_client:
            await client.aclose()
    return tickets


def is_unregistered(ticket: dict) -> bool:
    """Aparelho desinstalou o app ou revogou a permissão: apagar o token"""
    return (
        ticket.get("status") == "error"
        and (ticket.get("details") or {}).get("error") == "DeviceNotRegistered"
    )
