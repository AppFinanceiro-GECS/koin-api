"""
Cadastro pelo código de um evento (stand).

O visitante cria a conta com o código impresso no banner, já entra no app e
confirma o e-mail com um código de 6 dígitos. Com o e-mail confirmado, a equipe
do stand marca o brinde como entregue no próprio celular dele (um por conta).

Cada conta ganha uma licença individual para usar o app inteiro. A linha em
event_signups é a marca de que a conta veio do evento.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.rate_limit import limiter
from app.core.security import get_password_hash, validate_password_or_raise
from app.core.services.email_service import email_service
from app.core.utils import utc_now
from app.models import EventSignup, License, LicenseType, User
from app.models.household import HouseholdMember, HouseholdRole
from app.modules.auth.schemas.auth import Token
from app.modules.auth.schemas.event_signup import (
    EventSignupCreate,
    EventSignupStatus,
    EventSignupVerify,
)
from app.modules.auth.services.auth_service import AuthService
from app.modules.auth.services.user_setup import setup_new_user

router = APIRouter(prefix="/event-signup")

# Muda quando o texto da caixa "Quero receber novidades" mudar no app
CONSENT_VERSION = "2026-11-evento-v1"
CODE_TTL = timedelta(minutes=30)
MAX_ATTEMPTS = 5
RESEND_INTERVAL = timedelta(seconds=60)
MAX_SENDS = 5
EVENT_LICENSE_MAX_USERS = 4
EVENT_LICENSE_MAX_DOCUMENTS = 10


DEV_SOURCE = "dev"


def _event_is_open() -> bool:
    if not settings.event_signup_code:
        return False
    return not (settings.event_signup_ends_at and utc_now() > settings.event_signup_ends_at)


def _same_code(typed: str, expected: str) -> bool:
    return hmac.compare_digest(typed.strip().upper().encode(), expected.strip().upper().encode())


def _source_for(typed: str) -> str | None:
    """Origem do cadastro pelo código digitado; None se o código não vale agora."""
    if _event_is_open() and _same_code(typed, settings.event_signup_code or ""):
        return settings.event_signup_source
    if settings.event_signup_dev_code and _same_code(typed, settings.event_signup_dev_code):
        return DEV_SOURCE
    return None


def _hash_code(code: str) -> str:
    return hmac.new(settings.secret_key.encode(), code.encode(), hashlib.sha256).hexdigest()


def _new_code(signup: EventSignup) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = utc_now()
    signup.verification_code_hash = _hash_code(code)
    signup.verification_expires_at = now + CODE_TTL
    signup.verification_attempts = 0
    signup.verification_sent_at = now
    signup.verification_sends += 1
    return code


async def _signup_of(user: User, db: DbSession) -> EventSignup:
    signup = await db.scalar(select(EventSignup).where(EventSignup.user_id == user.id))
    if not signup:
        raise HTTPException(status_code=404, detail="Esta conta não foi criada no evento")
    return signup


def _status(user: User, signup: EventSignup) -> EventSignupStatus:
    return EventSignupStatus(
        source=signup.source,
        ticket_number=signup.id,
        name=user.name,
        email=user.email,
        email_verified=signup.email_verified_at is not None,
        marketing_opt_in=signup.marketing_opt_in,
        gift_delivered=signup.gift_delivered_at is not None,
    )


@router.post("", response_model=Token, status_code=201)
# No stand todo mundo sai pelo mesmo IP do Wi-Fi: o limite é por IP, então folgado
@limiter.limit("30/minute")
async def create_event_signup(
    request: Request,
    data: EventSignupCreate,
    db: DbSession,
    background_tasks: BackgroundTasks,
):
    """Cria a conta com o código do evento e manda o código de confirmação por e-mail."""
    if not _event_is_open() and not settings.event_signup_dev_code:
        raise HTTPException(status_code=404, detail="Não há evento com cadastro aberto agora")
    source = _source_for(data.code)
    if source is None:
        raise HTTPException(status_code=400, detail="Código do evento inválido")

    if await db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(
            status_code=400, detail="Este e-mail já tem conta. Entre com sua senha."
        )

    validate_password_or_raise(data.password)

    license = License(
        key=secrets.token_urlsafe(32),
        type=LicenseType.TRIAL,
        max_users=EVENT_LICENSE_MAX_USERS,
        max_documents_per_month=EVENT_LICENSE_MAX_DOCUMENTS,
        owner_email=data.email,
        notes=f"Cadastro no evento {source}",
    )
    db.add(license)
    await db.flush()

    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        name=data.name.strip(),
        is_verified=False,
        license_id=license.id,
    )
    db.add(user)
    await db.flush()

    license.owner_user_id = user.id
    db.add(
        HouseholdMember(
            license_id=license.id,
            user_id=user.id,
            role=HouseholdRole.OWNER.value,
            can_invite_members=True,
            can_see_all=True,
        )
    )
    await setup_new_user(db, user.id)

    now = utc_now()
    signup = EventSignup(
        user_id=user.id,
        source=source,
        marketing_opt_in=data.marketing_opt_in,
        marketing_opt_in_at=now if data.marketing_opt_in else None,
        consent_version=CONSENT_VERSION,
        verification_sends=0,
        verification_attempts=0,
    )
    code = _new_code(signup)
    db.add(signup)
    await db.commit()

    background_tasks.add_task(
        email_service.send_event_verification_code, user.email, user.name, code
    )
    return await AuthService(db).login(data.email, data.password)


@router.get("/me", response_model=EventSignupStatus)
async def get_event_signup(current_user: CurrentUser, db: DbSession):
    """Situação do cadastro no evento: e-mail confirmado e brinde entregue."""
    signup = await _signup_of(current_user, db)
    return _status(current_user, signup)


@router.post("/verify", response_model=EventSignupStatus)
async def verify_event_signup(data: EventSignupVerify, current_user: CurrentUser, db: DbSession):
    """Confirma o e-mail com o código de 6 dígitos."""
    signup = await _signup_of(current_user, db)
    if signup.email_verified_at:
        return _status(current_user, signup)

    if (
        not signup.verification_code_hash
        or not signup.verification_expires_at
        or utc_now() > signup.verification_expires_at
    ):
        raise HTTPException(status_code=400, detail="O código expirou. Peça um novo.")
    if signup.verification_attempts >= MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Muitas tentativas. Peça um novo código.")

    if not hmac.compare_digest(_hash_code(data.code), signup.verification_code_hash):
        signup.verification_attempts += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Código incorreto")

    signup.email_verified_at = utc_now()
    signup.verification_code_hash = None
    current_user.is_verified = True
    await db.commit()
    return _status(current_user, signup)


@router.post("/resend", status_code=202)
async def resend_event_code(
    current_user: CurrentUser, db: DbSession, background_tasks: BackgroundTasks
):
    """Manda um código novo (no máximo 1 por minuto e 5 no total)."""
    signup = await _signup_of(current_user, db)
    if signup.email_verified_at:
        raise HTTPException(status_code=400, detail="E-mail já confirmado")
    if signup.verification_sends >= MAX_SENDS:
        raise HTTPException(status_code=429, detail="Limite de reenvios atingido")
    if signup.verification_sent_at and utc_now() - signup.verification_sent_at < RESEND_INTERVAL:
        raise HTTPException(status_code=429, detail="Aguarde um minuto para pedir outro código")

    code = _new_code(signup)
    await db.commit()
    background_tasks.add_task(
        email_service.send_event_verification_code, current_user.email, current_user.name, code
    )
    return {"message": "Código reenviado"}


@router.post("/gift", response_model=EventSignupStatus)
async def deliver_event_gift(current_user: CurrentUser, db: DbSession):
    """A equipe do stand toca no celular do visitante ao entregar o brinde."""
    signup = await _signup_of(current_user, db)
    if not signup.email_verified_at:
        raise HTTPException(status_code=400, detail="Confirme o e-mail antes de retirar o brinde")
    if signup.gift_delivered_at:
        raise HTTPException(status_code=409, detail="O brinde desta conta já foi entregue")

    signup.gift_delivered_at = utc_now()
    await db.commit()
    return _status(current_user, signup)
