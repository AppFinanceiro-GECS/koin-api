"""
Cash Calendar Module.

Provides daily/weekly visualization of cash flow combining
confirmed transactions with future projections.
"""

from .routers.cash_calendar import router

__all__ = ["router"]
