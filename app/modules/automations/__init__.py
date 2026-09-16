"""
Financial Automations Module

Provides automation rules for automatic financial operations based on
triggers (schedule, events, thresholds).
"""

from .routers.automations import router

__all__ = ["router"]
