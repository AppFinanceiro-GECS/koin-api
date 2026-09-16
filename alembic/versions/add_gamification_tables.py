"""Add gamification tables

Revision ID: add_gamification_tables
Revises: remove_envelopes_tables
Create Date: 2025-01-25

Sistema de gamificação:
- badge_definitions: Catálogo de badges
- user_badges: Badges conquistados
- user_streaks: Streaks ativos
- streak_history: Histórico de streaks
- challenge_definitions: Catálogo de desafios
- user_challenges: Progresso em desafios
- user_points: Saldo de pontos
- points_transactions: Histórico de pontos
"""

import sqlalchemy as sa

from alembic import op

revision = "add_gamification_tables"
down_revision = "remove_envelopes_tables"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Badge Definitions
    op.create_table(
        "badge_definitions",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("icon", sa.String(50), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("rarity", sa.String(20), nullable=False),
        sa.Column("points_reward", sa.Integer(), default=10),
        sa.Column("criteria_type", sa.String(50), nullable=False),
        sa.Column("criteria_value", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), default=0),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("is_secret", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 2. User Badges
    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "badge_id",
            sa.String(50),
            sa.ForeignKey("badge_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("earned_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("seen_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_badges_user_id", "user_badges", ["user_id"])
    op.create_index("ix_user_badges_badge_id", "user_badges", ["badge_id"])
    op.create_unique_constraint("uq_user_badges_user_badge", "user_badges", ["user_id", "badge_id"])

    # 3. User Streaks
    op.create_table(
        "user_streaks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("streak_type", sa.String(30), nullable=False),
        sa.Column("current_count", sa.Integer(), default=0),
        sa.Column("longest_count", sa.Integer(), default=0),
        sa.Column("last_action_date", sa.Date(), nullable=True),
        sa.Column("freeze_available", sa.Integer(), default=1),
        sa.Column("freeze_used_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
    )
    op.create_index("ix_user_streaks_user_id", "user_streaks", ["user_id"])
    op.create_unique_constraint(
        "uq_user_streaks_user_type", "user_streaks", ["user_id", "streak_type"]
    )

    # 4. Streak History
    op.create_table(
        "streak_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("streak_type", sa.String(30), nullable=False),
        sa.Column("started_at", sa.Date(), nullable=False),
        sa.Column("ended_at", sa.Date(), nullable=False),
        sa.Column("final_count", sa.Integer(), nullable=False),
        sa.Column("ended_reason", sa.String(20), nullable=False),
    )
    op.create_index("ix_streak_history_user_id", "streak_history", ["user_id"])

    # 5. Challenge Definitions
    op.create_table(
        "challenge_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("icon", sa.String(50), nullable=False),
        sa.Column("difficulty", sa.String(20), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("challenge_type", sa.String(50), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("points_reward", sa.Integer(), default=50),
        sa.Column(
            "badge_reward_id",
            sa.String(50),
            sa.ForeignKey("badge_definitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column("available_until", sa.Date(), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), default=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 6. User Challenges
    op.create_table(
        "user_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "challenge_id",
            sa.Integer(),
            sa.ForeignKey("challenge_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("progress", sa.JSON(), default=dict),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_challenges_user_id", "user_challenges", ["user_id"])
    op.create_index("ix_user_challenges_status", "user_challenges", ["status"])

    # 7. User Points
    op.create_table(
        "user_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("current_points", sa.Integer(), default=0),
        sa.Column("lifetime_points", sa.Integer(), default=0),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()
        ),
    )
    op.create_index("ix_user_points_user_id", "user_points", ["user_id"])

    # 8. Points Transactions
    op.create_table(
        "points_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=True),
        sa.Column("reference_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_points_transactions_user_id", "points_transactions", ["user_id"])

    # 9. Seed inicial de badges
    op.execute("""
        INSERT INTO badge_definitions (id, name, description, icon, category, rarity, points_reward, criteria_type, criteria_value, display_order) VALUES
        -- Registro
        ('first_transaction', 'Primeiro Passo', 'Registrou sua primeira transação', 'Plus', 'registro', 'common', 10, 'transaction_count', 1, 1),
        ('transactions_10', 'Começando', 'Registrou 10 transações', 'TrendingUp', 'registro', 'common', 20, 'transaction_count', 10, 2),
        ('transactions_50', 'Consistente', 'Registrou 50 transações', 'Award', 'registro', 'uncommon', 50, 'transaction_count', 50, 3),
        ('transactions_100', 'Organizador', 'Registrou 100 transações', 'Medal', 'registro', 'rare', 100, 'transaction_count', 100, 4),
        ('transactions_500', 'Meticuloso', 'Registrou 500 transações', 'Crown', 'registro', 'epic', 250, 'transaction_count', 500, 5),
        ('transactions_1000', 'Arquivista', 'Registrou 1000 transações', 'Trophy', 'registro', 'legendary', 500, 'transaction_count', 1000, 6),

        -- Streaks
        ('streak_7', 'Semana de Fogo', '7 dias consecutivos registrando', 'Flame', 'streak', 'common', 25, 'streak_days', 7, 10),
        ('streak_14', 'Duas Semanas', '14 dias consecutivos registrando', 'Flame', 'streak', 'uncommon', 50, 'streak_days', 14, 11),
        ('streak_30', 'Mês Impecável', '30 dias consecutivos registrando', 'Flame', 'streak', 'rare', 100, 'streak_days', 30, 12),
        ('streak_60', 'Bimestre Perfeito', '60 dias consecutivos registrando', 'Flame', 'streak', 'epic', 200, 'streak_days', 60, 13),
        ('streak_100', 'Centenário', '100 dias consecutivos registrando', 'Flame', 'streak', 'epic', 300, 'streak_days', 100, 14),
        ('streak_365', 'Lendário', '365 dias consecutivos registrando', 'Star', 'streak', 'legendary', 1000, 'streak_days', 365, 15),

        -- Economia
        ('first_goal', 'Pé de Meia', 'Criou sua primeira meta de economia', 'Target', 'economia', 'common', 15, 'goal_created', 1, 20),
        ('goal_completed', 'Meta Atingida', 'Completou sua primeira meta', 'CheckCircle', 'economia', 'uncommon', 50, 'goal_completed', 1, 21),
        ('goals_3', 'Planejador', 'Completou 3 metas financeiras', 'CircleCheck', 'economia', 'rare', 100, 'goal_completed', 3, 22),
        ('saved_1000', 'Guardião', 'Economizou R$1.000 no total', 'PiggyBank', 'economia', 'rare', 100, 'total_saved', 1000, 23),
        ('saved_10000', 'Cofre de Ouro', 'Economizou R$10.000 no total', 'Vault', 'economia', 'epic', 500, 'total_saved', 10000, 24),

        -- Controle
        ('month_positive', 'No Azul', 'Primeiro mês com saldo positivo', 'ThumbsUp', 'controle', 'uncommon', 50, 'month_positive', 1, 30),
        ('months_positive_3', 'Equilibrista', '3 meses consecutivos no azul', 'Scale', 'controle', 'rare', 150, 'months_positive', 3, 31),
        ('months_positive_6', 'Controlado', '6 meses consecutivos no azul', 'ShieldCheck', 'controle', 'epic', 300, 'months_positive', 6, 32),
        ('months_positive_12', 'Mestre do Orçamento', '12 meses consecutivos no azul', 'Crown', 'controle', 'legendary', 600, 'months_positive', 12, 33),
        ('budget_master', 'Rei do Orçamento', 'Ficou dentro do orçamento por 3 meses', 'Wallet', 'controle', 'rare', 100, 'budget_on_track', 3, 34),

        -- Dívidas
        ('first_debt_paid', 'Libertador', 'Quitou sua primeira dívida', 'Unlock', 'dividas', 'uncommon', 50, 'debt_paid', 1, 40),
        ('debts_3_paid', 'Livre', 'Quitou 3 dívidas', 'KeyRound', 'dividas', 'rare', 100, 'debt_paid', 3, 41),
        ('all_debts_paid', 'Sem Correntes', 'Quitou todas as dívidas', 'PartyPopper', 'dividas', 'epic', 200, 'all_debts_paid', 1, 42),

        -- Especial
        ('early_adopter', 'Pioneiro', 'Um dos primeiros usuários do Biveto', 'Rocket', 'especial', 'legendary', 100, 'special', 1, 50);
    """)

    # 10. Seed inicial de desafios
    op.execute("""
        INSERT INTO challenge_definitions (name, description, icon, difficulty, duration_days, challenge_type, criteria, points_reward, is_recurring) VALUES
        ('Registro Perfeito', 'Registre todas as suas transações por 30 dias seguidos', 'Calendar', 'hard', 30, 'register_streak', '{"days": 30}', 100, true),
        ('Semana Econômica', 'Não gaste mais que o orçamento por 7 dias', 'Wallet', 'medium', 7, 'budget_compliance', '{"days": 7}', 50, true),
        ('Economia 10%', 'Economize pelo menos 10% da sua renda este mês', 'PiggyBank', 'medium', 30, 'save_percentage', '{"percentage": 10}', 75, true),
        ('Economia 20%', 'Economize pelo menos 20% da sua renda este mês', 'PiggyBank', 'hard', 30, 'save_percentage', '{"percentage": 20}', 150, true),
        ('Semana Sem Delivery', 'Passe 7 dias sem gastar com delivery', 'UtensilsCrossed', 'easy', 7, 'no_spending_category', '{"category_name": "Delivery", "days": 7}', 40, true),
        ('Controle de Gastos', 'Reduza seus gastos em 15% comparado ao mês anterior', 'TrendingDown', 'hard', 30, 'reduce_spending', '{"percentage": 15}', 120, true);
    """)


def downgrade():
    op.drop_table("points_transactions")
    op.drop_table("user_points")
    op.drop_table("user_challenges")
    op.drop_table("challenge_definitions")
    op.drop_table("streak_history")
    op.drop_table("user_streaks")
    op.drop_table("user_badges")
    op.drop_table("badge_definitions")
