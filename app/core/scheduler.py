"""
APScheduler configuration for background tasks.
Replaces Celery Beat — runs inside the FastAPI process, no Redis needed.

Usage:
    from app.core.scheduler import scheduler, start_scheduler, shutdown_scheduler

    # In FastAPI lifespan:
    await start_scheduler()
    yield
    shutdown_scheduler()
"""

import asyncio
import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import or_, select

from app.core.utils import today_br

from .config import settings
from .database import async_session_maker
from .modules import enabled_modules
from .services.email_service import email_service
from .utils import utc_now

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

# When True, tasks log what they would do but don't send notifications
DRY_RUN = getattr(settings, "scheduler_dry_run", False)

# On first run, only process items from the last N days (avoid backlog spam)
BACKLOG_WINDOW_DAYS = 7


async def _get_active_users():
    """Get all active users."""
    from app.models.user import User

    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.is_active == True))
        return result.scalars().all()


async def _run_alert_for_all_users(alert_method_name: str):
    """Run a specific AlertEngine method for all active users."""
    from app.modules.notifications.services.alert_engine import AlertEngine

    users = await _get_active_users()
    total = 0

    for user in users:
        try:
            async with async_session_maker() as db:
                engine = AlertEngine(db)
                count = await getattr(engine, alert_method_name)(user)
                if not DRY_RUN:
                    await db.commit()
                else:
                    await db.rollback()
                    logger.info(
                        f"[DRY RUN] {alert_method_name} would send {count} notifications for user {user.id}"
                    )
                total += count
        except Exception as e:
            logger.exception(f"Error in {alert_method_name} for user {user.id}: {e}")

    logger.info(
        f"Scheduler: {alert_method_name} completed — {total} notifications {'(dry run)' if DRY_RUN else 'sent'}"
    )
    return total


# ===== Documents (RN016 / #37) =====


async def task_retry_waiting_documents():
    from app.modules.documents.services.document_service import retry_waiting_documents

    try:
        processed = await retry_waiting_documents()
        if processed:
            logger.info(f"Scheduler: {processed} documentos reprocessados")
    except Exception as e:
        logger.exception(f"Error retrying waiting documents: {e}")


async def task_purge_expired_documents():
    from app.modules.documents.services.retention import purge_expired_documents

    try:
        async with async_session_maker() as session:
            await purge_expired_documents(session)
    except Exception as e:
        logger.exception(f"Error purging expired documents: {e}")


# ===== Alert Tasks =====


async def task_check_invoice_due_dates():
    await _run_alert_for_all_users("check_invoice_due_dates")


async def task_check_budget_thresholds():
    await _run_alert_for_all_users("check_budget_thresholds")


async def task_check_credit_card_limits():
    await _run_alert_for_all_users("check_credit_card_limits")


async def task_check_goal_milestones():
    await _run_alert_for_all_users("check_goal_milestones")


async def task_check_recurring_due():
    await _run_alert_for_all_users("check_recurring_due")


async def task_check_low_balance():
    await _run_alert_for_all_users("check_low_balance")


# ===== Email Notification Delivery =====


async def _send_pending_email_notifications(db) -> int:
    """
    Send notifications that are generated but not yet delivered by email.
    Respects per-type preference (NotificationPreference.email_enabled) and the
    global opt-out (NotificationSettings.email_unsubscribed). Only marks a
    notification as sent after the email actually goes out, so a failed send
    is retried on the next run instead of being silently lost.
    Returns the number of emails sent.
    """
    from app.models.notification import (
        Notification,
        NotificationSettings,
        NotificationType,
    )
    from app.models.user import User
    from app.modules.notifications.services.notification_service import NotificationService

    now = utc_now()
    notification_service = NotificationService(db)
    sent_count = 0

    result = await db.execute(
        select(Notification, User)
        .join(User, Notification.user_id == User.id)
        .where(
            Notification.sent_email == False,  # noqa: E712
            Notification.is_dismissed == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
            or_(Notification.scheduled_for.is_(None), Notification.scheduled_for <= now),
        )
    )

    for notification, user in result.all():
        try:
            settings_result = await db.execute(
                select(NotificationSettings).where(NotificationSettings.user_id == user.id)
            )
            user_settings = settings_result.scalar_one_or_none()
            if user_settings and user_settings.email_unsubscribed:
                continue

            preference = await notification_service._get_or_create_preference(
                user.id, NotificationType(notification.type)
            )
            if not preference.email_enabled or preference.frequency == "disabled":
                continue

            if DRY_RUN:
                logger.info(
                    f"[DRY RUN] Would email notification {notification.id} to user {user.id}"
                )
                continue

            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(
                None,
                email_service.send_notification_email,
                user.email,
                user.name,
                notification.title,
                notification.message,
                notification.action_url,
                notification.action_label,
            )

            if success:
                notification.sent_email = True
                notification.sent_at = now
                await db.commit()
                sent_count += 1
            else:
                # Nothing to undo: sent_email stays False and is retried next run.
                logger.warning(f"Failed to email notification {notification.id} (user {user.id})")
        except Exception:
            await db.rollback()
            logger.exception(f"Error emailing notification {notification.id}")

    return sent_count


async def task_send_pending_email_notifications():
    async with async_session_maker() as db:
        count = await _send_pending_email_notifications(db)
    logger.info(f"Scheduler: email notifications — {count} sent{' (dry run)' if DRY_RUN else ''}")


# ===== Recurring Transaction Generation =====


def _advance_next_due_date(rec):
    """Calculate and set the next due date based on the recurrence frequency."""
    from dateutil.relativedelta import relativedelta

    current = rec.next_due_date
    freq = rec.frequency

    if freq == "daily":
        rec.next_due_date = current + timedelta(days=1)
    elif freq == "weekly":
        rec.next_due_date = current + timedelta(weeks=1)
    elif freq == "monthly":
        rec.next_due_date = current + relativedelta(months=1)
        # Respect day_of_month if set (e.g., always on the 15th)
        if rec.day_of_month:
            import calendar

            year = rec.next_due_date.year
            month = rec.next_due_date.month
            max_day = calendar.monthrange(year, month)[1]
            day = min(rec.day_of_month, max_day)
            rec.next_due_date = rec.next_due_date.replace(day=day)
    elif freq == "yearly":
        rec.next_due_date = current + relativedelta(years=1)
    else:
        # Fallback: monthly
        rec.next_due_date = current + relativedelta(months=1)

    # If end_date is set and next_due_date exceeds it, deactivate
    if rec.end_date and rec.next_due_date > rec.end_date:
        rec.status = "cancelled"
        rec.next_due_date = None


async def task_generate_recurring_transactions():
    """Generate transactions from recurring definitions that are due."""
    from sqlalchemy import and_

    from app.models.recurring import RecurringTransaction
    from app.models.transaction import Transaction

    today = today_br()
    generated = 0

    async with async_session_maker() as db:
        # Get all active recurring with next_due_date <= today
        result = await db.execute(
            select(RecurringTransaction).where(
                and_(
                    RecurringTransaction.status == "active",
                    RecurringTransaction.next_due_date <= today,
                    RecurringTransaction.next_due_date.isnot(None),
                )
            )
        )
        recurring_items = result.scalars().all()

        for rec in recurring_items:
            try:
                # Process all due dates up to today (catch up if missed)
                while rec.next_due_date and rec.next_due_date <= today and rec.status == "active":
                    # Idempotency: check if transaction already exists for this date
                    existing = await db.execute(
                        select(Transaction).where(
                            and_(
                                Transaction.recurring_id == rec.id,
                                Transaction.date == rec.next_due_date,
                            )
                        )
                    )
                    if existing.scalar_one_or_none():
                        # Already generated, just advance
                        _advance_next_due_date(rec)
                        continue

                    # Create transaction
                    transaction = Transaction(
                        user_id=rec.user_id,
                        account_id=rec.account_id,
                        category_id=rec.category_id,
                        amount=rec.amount,
                        description=rec.description or rec.name,
                        date=rec.next_due_date,
                        type=rec.type,
                        payment_method=rec.payment_method,
                        recurring_id=rec.id,
                        is_recurring=True,
                        recurrence_type=rec.frequency,
                        is_paid=False,
                        is_fixed=True,
                        ownership_type=rec.ownership_type,
                    )
                    db.add(transaction)

                    # Update recurring
                    rec.last_generated_date = rec.next_due_date
                    _advance_next_due_date(rec)

                    generated += 1
            except Exception as e:
                logger.exception(f"Error generating recurring {rec.id}: {e}")

        if generated > 0:
            await db.commit()

    logger.info(f"Scheduler: generated {generated} recurring transactions")


# ===== Automation Tasks =====


async def task_process_scheduled_automations():
    """Process scheduled automation rules."""
    from datetime import datetime

    from app.models import AutomationRule, TriggerType
    from app.modules.automations.services import AutomationService, should_run_scheduled

    try:
        async with async_session_maker() as session:
            now = datetime.now()
            current_time = now.time()
            current_date = now.date()

            result = await session.execute(
                select(AutomationRule).where(
                    AutomationRule.is_active == True,
                    AutomationRule.trigger_type == TriggerType.SCHEDULE.value,
                )
            )
            rules = result.scalars().all()
            service = AutomationService(session)
            executed = 0

            for rule in rules:
                try:
                    if not should_run_scheduled(rule, current_date, current_time):
                        continue

                    if rule.last_executed_at:
                        last_date = rule.last_executed_at.date()
                        freq = rule.trigger_config.get("frequency", "daily")
                        if freq == "daily" and last_date == current_date:
                            continue
                        elif (
                            freq == "weekly"
                            and last_date.isocalendar()[1] == current_date.isocalendar()[1]
                        ):
                            continue
                        elif (
                            freq == "monthly"
                            and last_date.year == current_date.year
                            and last_date.month == current_date.month
                        ):
                            continue

                    if DRY_RUN:
                        logger.info(
                            f"[DRY RUN] Would execute scheduled rule {rule.id}: {rule.name}"
                        )
                    else:
                        trigger_reason = f"schedule:{rule.trigger_config.get('frequency')}:{current_date.isoformat()}"
                        await service.execute_rule(rule, trigger_reason)
                        executed += 1
                except Exception as e:
                    logger.exception(f"Error processing rule {rule.id}: {e}")

            if not DRY_RUN:
                await session.commit()
            logger.info(
                f"Scheduler: scheduled automations — {executed} executed {'(dry run)' if DRY_RUN else ''}"
            )
    except Exception as e:
        logger.exception(f"Error in scheduled automations: {e}")


async def task_process_threshold_automations():
    """Process threshold-based automation rules."""
    from app.models import AutomationRule, TriggerType
    from app.modules.automations.services import AutomationService

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(AutomationRule).where(
                    AutomationRule.is_active == True,
                    AutomationRule.trigger_type == TriggerType.THRESHOLD.value,
                )
            )
            rules = result.scalars().all()
            service = AutomationService(session)
            executed = 0
            today = today_br()

            for rule in rules:
                try:
                    if rule.last_executed_at and rule.last_executed_at.date() == today:
                        continue

                    conditions_met, _ = await service._evaluate_conditions(rule, None)
                    if conditions_met:
                        if DRY_RUN:
                            logger.info(
                                f"[DRY RUN] Would execute threshold rule {rule.id}: {rule.name}"
                            )
                        else:
                            trigger_reason = f"threshold:{rule.trigger_config.get('threshold_type')}:{today.isoformat()}"
                            await service.execute_rule(rule, trigger_reason)
                            executed += 1
                except Exception as e:
                    logger.exception(f"Error processing threshold rule {rule.id}: {e}")

            if not DRY_RUN:
                await session.commit()
            logger.info(
                f"Scheduler: threshold automations — {executed} executed {'(dry run)' if DRY_RUN else ''}"
            )
    except Exception as e:
        logger.exception(f"Error in threshold automations: {e}")


# ===== Scheduler Setup =====


# (módulo dono, função, gatilho, id). Job de módulo desligado não é agendado (#42)
JOBS = [
    # Alert tasks — same schedule as old Celery Beat
    (
        "invoices",
        task_check_invoice_due_dates,
        CronTrigger(hour=8, minute=0),
        "check_invoice_due_dates",
    ),
    (
        "budgets",
        task_check_budget_thresholds,
        CronTrigger(hour="0,6,12,18", minute=15),
        "check_budget_thresholds",
    ),
    (
        "credit-cards",
        task_check_credit_card_limits,
        CronTrigger(hour="0,6,12,18", minute=30),
        "check_credit_card_limits",
    ),
    (
        "goals",
        task_check_goal_milestones,
        CronTrigger(hour="9,18", minute=0),
        "check_goal_milestones",
    ),
    ("recurring", task_check_recurring_due, CronTrigger(hour=18, minute=0), "check_recurring_due"),
    ("accounts", task_check_low_balance, CronTrigger(hour=9, minute=30), "check_low_balance"),
    # Email delivery for pending notifications — every 5 minutes
    (
        "notifications",
        task_send_pending_email_notifications,
        IntervalTrigger(minutes=5),
        "send_pending_email_notifications",
    ),
    # Recurring transaction generation — run daily at 6:00 AM
    (
        "recurring",
        task_generate_recurring_transactions,
        CronTrigger(hour=6, minute=0),
        "generate_recurring_transactions",
    ),
    # Documentos esperando a IA e processamento preso — a cada 5 minutos
    (
        "documents",
        task_retry_waiting_documents,
        IntervalTrigger(minutes=5),
        "retry_waiting_documents",
    ),
    # Retenção das faturas enviadas (#50) — diário, fora do horário de uso
    (
        "documents",
        task_purge_expired_documents,
        CronTrigger(hour=3, minute=30),
        "purge_expired_documents",
    ),
    # Automation tasks
    (
        "automations",
        task_process_scheduled_automations,
        CronTrigger(minute=0),
        "process_scheduled_automations",
    ),
    (
        "automations",
        task_process_threshold_automations,
        CronTrigger(hour="0,6,12,18", minute=45),
        "process_threshold_automations",
    ),
]


def register_jobs():
    """Register the jobs of the enabled modules. Called once at startup."""
    modules = enabled_modules()
    for module, func, trigger, job_id in JOBS:
        if module in modules:
            scheduler.add_job(func, trigger, id=job_id, replace_existing=True)

    logger.info(f"Scheduler: {len(scheduler.get_jobs())} jobs registered (dry_run={DRY_RUN})")


async def start_scheduler():
    """Start the scheduler. Call from FastAPI lifespan."""
    register_jobs()
    scheduler.start()
    logger.info("Scheduler started.")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
