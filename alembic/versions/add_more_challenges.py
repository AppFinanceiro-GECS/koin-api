"""Add more default challenges

Revision ID: add_more_challenges
Revises: add_gamification_tables
Create Date: 2025-01-26

Adiciona mais desafios padrão para gamificação
"""

from alembic import op

revision = "add_more_challenges"
down_revision = "add_gamification_tables"
branch_labels = None
depends_on = None


def upgrade():
    # Adicionar mais desafios variados
    op.execute("""
        INSERT INTO challenge_definitions (name, description, icon, difficulty, duration_days, challenge_type, criteria, points_reward, is_recurring) VALUES
        -- Desafios semanais fáceis
        ('Primeira Semana', 'Registre pelo menos 1 transação por dia durante 7 dias', 'Calendar', 'easy', 7, 'register_streak', '{"days": 7}', 30, true),
        ('Sem Supérfluos', 'Passe 5 dias sem gastar em compras supérfluas', 'ShoppingBag', 'easy', 5, 'no_spending_category', '{"category_name": "Compras", "days": 5}', 35, true),
        ('Café em Casa', 'Passe 7 dias sem comprar café fora', 'Coffee', 'easy', 7, 'no_spending_category', '{"category_name": "Alimentação", "days": 7}', 40, true),

        -- Desafios de médio prazo
        ('Quinzena Organizada', 'Registre transações por 15 dias seguidos', 'CalendarCheck', 'medium', 15, 'register_streak', '{"days": 15}', 60, true),
        ('Economia 5%', 'Economize pelo menos 5% da sua renda este mês', 'Coins', 'easy', 30, 'save_percentage', '{"percentage": 5}', 50, true),
        ('Transporte Consciente', 'Reduza gastos com transporte em 10%', 'Car', 'medium', 30, 'reduce_spending', '{"percentage": 10, "category": "Transporte"}', 70, true),

        -- Desafios de longo prazo
        ('Mestre do Registro', 'Registre transações por 60 dias seguidos', 'Award', 'hard', 60, 'register_streak', '{"days": 60}', 200, true),
        ('Super Economizador', 'Economize 30% da sua renda este mês', 'Vault', 'hard', 30, 'save_percentage', '{"percentage": 30}', 200, true),

        -- Desafios especiais
        ('Fim de Semana Econômico', 'Não gaste nada no fim de semana', 'Calendar', 'medium', 2, 'no_spending_category', '{"category_name": "all", "days": 2}', 45, true),
        ('Meta Cumprida', 'Complete uma meta de economia', 'Target', 'medium', 30, 'goal_completed', '{"count": 1}', 80, true),
        ('Dívida Zero', 'Quite uma dívida este mês', 'Unlock', 'hard', 30, 'debt_paid', '{"count": 1}', 100, true),
        ('Orçamento Perfeito', 'Fique dentro do orçamento em todas as categorias', 'Wallet', 'hard', 30, 'budget_compliance', '{"days": 30}', 150, true);
    """)


def downgrade():
    # Remove os desafios adicionados
    op.execute("""
        DELETE FROM challenge_definitions WHERE name IN (
            'Primeira Semana',
            'Sem Supérfluos',
            'Café em Casa',
            'Quinzena Organizada',
            'Economia 5%',
            'Transporte Consciente',
            'Mestre do Registro',
            'Super Economizador',
            'Fim de Semana Econômico',
            'Meta Cumprida',
            'Dívida Zero',
            'Orçamento Perfeito'
        );
    """)
