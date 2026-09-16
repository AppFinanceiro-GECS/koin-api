from app.modules.known_services.models.known_service import KnownRecurringService

from .account import Account
from .api_key import APIKey, APIKeyStatus

# Envelope module removed - functionality merged into Budgets module
# from .envelope import (
#     SpendingEnvelope,
#     EnvelopeHistory,
#     EnvelopePeriodType,
#     EnvelopeStatus,
#     EnvelopeRefillSchedule,
#     EnvelopeChangeType,
# )
from .automation_rule import (
    ActionType,
    AutomationExecution,
    AutomationRule,
    EventType,
    ScheduleFrequency,
    ThresholdType,
    TriggerType,
)
from .benefit_card import BenefitCard, BenefitCardProvider, BenefitCardType
from .budget import Budget, BudgetItem, BudgetPeriodType
from .category import Category
from .chat import (
    ChatConversation,
    ChatMessage,
    MessageRole,
)
from .credit_card import CreditCard, PointsProgram
from .credit_card_invoice import CreditCardInvoice, InvoiceStatus
from .debt import Debt, DebtPayment, DebtStatus, DebtType, PayoffStrategy
from .document import Document, DocumentExtraction
from .gamification import (
    BadgeCategory,
    BadgeDefinition,
    BadgeRarity,
    ChallengeDefinition,
    ChallengeDifficulty,
    ChallengeStatus,
    PointsTransaction,
    StreakHistory,
    StreakType,
    UserBadge,
    UserChallenge,
    UserPoints,
    UserStreak,
)
from .goal import Goal, GoalContribution, GoalStatus, GoalType
from .grocery import (
    GROCERY_CATEGORY_DISPLAY,
    NECESSITY_TYPE_DISPLAY,
    GroceryCategory,
    GroceryPriceHistory,
    GroceryProduct,
    GroceryPurchase,
    NecessityType,
    ShoppingList,
    ShoppingListItem,
    ShoppingListSource,
    ShoppingListStatus,
)
from .household import HouseholdMember, HouseholdRole, OwnershipType
from .income_source import IncomeFrequency, IncomeSource, IncomeType
from .income_split_rule import IncomeSplitRule, SplitType
from .installment import InstallmentSeries, InstallmentSeriesStatus
from .invitation import Invitation, InvitationStatus
from .license import License, LicenseStatus, LicenseType
from .merchant import Merchant
from .notification import (
    Notification,
    NotificationFrequency,
    NotificationPreference,
    NotificationPriority,
    NotificationSettings,
    NotificationType,
    PushSubscription,
)
from .receipt import (
    RECEIPT_STATUS_DISPLAY,
    Receipt,
    ReceiptPayment,
    ReceiptStatus,
)
from .recurring import RecurrenceFrequency, RecurringStatus, RecurringTransaction
from .rule import UserMerchantRule
from .transaction import Transaction, TransactionAudit
from .transaction_payment import TransactionPayment
from .user import User

__all__ = [
    "License",
    "LicenseType",
    "LicenseStatus",
    "User",
    "Account",
    "HouseholdMember",
    "HouseholdRole",
    "OwnershipType",
    "Category",
    "Merchant",
    "Document",
    "DocumentExtraction",
    "Transaction",
    "TransactionAudit",
    "UserMerchantRule",
    "InstallmentSeries",
    "InstallmentSeriesStatus",
    "Budget",
    "BudgetItem",
    "BudgetPeriodType",
    "Goal",
    "GoalContribution",
    "GoalType",
    "GoalStatus",
    "Debt",
    "DebtPayment",
    "DebtType",
    "DebtStatus",
    "PayoffStrategy",
    "Invitation",
    "InvitationStatus",
    "RecurringTransaction",
    "RecurrenceFrequency",
    "RecurringStatus",
    "CreditCard",
    "PointsProgram",
    "BenefitCard",
    "BenefitCardType",
    "BenefitCardProvider",
    "TransactionPayment",
    "IncomeSource",
    "IncomeType",
    "IncomeFrequency",
    "IncomeSplitRule",
    "SplitType",
    "CreditCardInvoice",
    "InvoiceStatus",
    "APIKey",
    "APIKeyStatus",
    "Notification",
    "NotificationPreference",
    "NotificationSettings",
    "PushSubscription",
    "NotificationType",
    "NotificationPriority",
    "NotificationFrequency",
    # Envelope module removed - functionality merged into Budgets module
    # "SpendingEnvelope",
    # "EnvelopeHistory",
    # "EnvelopePeriodType",
    # "EnvelopeStatus",
    # "EnvelopeRefillSchedule",
    # "EnvelopeChangeType",
    "AutomationRule",
    "AutomationExecution",
    "TriggerType",
    "ActionType",
    "ScheduleFrequency",
    "EventType",
    "ThresholdType",
    "KnownRecurringService",
    "GroceryProduct",
    "GroceryPurchase",
    "GroceryPriceHistory",
    "ShoppingList",
    "ShoppingListItem",
    "GroceryCategory",
    "NecessityType",
    "ShoppingListStatus",
    "ShoppingListSource",
    "GROCERY_CATEGORY_DISPLAY",
    "NECESSITY_TYPE_DISPLAY",
    "Receipt",
    "ReceiptPayment",
    "ReceiptStatus",
    "RECEIPT_STATUS_DISPLAY",
    "ChatConversation",
    "ChatMessage",
    "MessageRole",
    # Gamification
    "BadgeDefinition",
    "UserBadge",
    "BadgeRarity",
    "BadgeCategory",
    "UserStreak",
    "StreakHistory",
    "StreakType",
    "ChallengeDefinition",
    "UserChallenge",
    "ChallengeDifficulty",
    "ChallengeStatus",
    "UserPoints",
    "PointsTransaction",
]
