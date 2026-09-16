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

import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select

from .config import settings
from .database import async_session_maker

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

    today = date.today()
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
            today = date.today()

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


# ===== Startup Migration Task =====


async def task_migrate_credit_card_transactions():
    """One-time migration: assign credit card transactions to invoices."""
    from app.main import migrate_credit_card_transactions

    logger.info("Scheduler: running credit card transaction migration...")
    await migrate_credit_card_transactions()
    logger.info("Scheduler: credit card migration complete.")


# ===== Scheduler Setup =====


def register_jobs():
    """Register all scheduled jobs. Called once at startup."""

    # Alert tasks — same schedule as old Celery Beat
    scheduler.add_job(
        task_check_invoice_due_dates,
        CronTrigger(hour=8, minute=0),
        id="check_invoice_due_dates",
        replace_existing=True,
    )
    scheduler.add_job(
        task_check_budget_thresholds,
        CronTrigger(hour="0,6,12,18", minute=15),
        id="check_budget_thresholds",
        replace_existing=True,
    )
    scheduler.add_job(
        task_check_credit_card_limits,
        CronTrigger(hour="0,6,12,18", minute=30),
        id="check_credit_card_limits",
        replace_existing=True,
    )
    scheduler.add_job(
        task_check_goal_milestones,
        CronTrigger(hour="9,18", minute=0),
        id="check_goal_milestones",
        replace_existing=True,
    )
    scheduler.add_job(
        task_check_recurring_due,
        CronTrigger(hour=18, minute=0),
        id="check_recurring_due",
        replace_existing=True,
    )
    scheduler.add_job(
        task_check_low_balance,
        CronTrigger(hour=9, minute=30),
        id="check_low_balance",
        replace_existing=True,
    )

    # Recurring transaction generation — run daily at 6:00 AM
    scheduler.add_job(
        task_generate_recurring_transactions,
        CronTrigger(hour=6, minute=0),
        id="generate_recurring_transactions",
        replace_existing=True,
    )

    # Automation tasks
    scheduler.add_job(
        task_process_scheduled_automations,
        CronTrigger(minute=0),
        id="process_scheduled_automations",
        replace_existing=True,
    )
    scheduler.add_job(
        task_process_threshold_automations,
        CronTrigger(hour="0,6,12,18", minute=45),
        id="process_threshold_automations",
        replace_existing=True,
    )

    # One-time startup migration — run 30s after boot
    scheduler.add_job(
        task_migrate_credit_card_transactions,
        DateTrigger(run_date=None),
        id="startup_migration",
        replace_existing=True,
    )

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
