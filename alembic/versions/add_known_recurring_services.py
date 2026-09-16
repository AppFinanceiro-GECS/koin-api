"""Add known_recurring_services table

Revision ID: add_known_services
Revises: add_payment_method
Create Date: 2026-01-13

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_known_services"
down_revision = "add_payment_method"
branch_labels = None
depends_on = None


# Seed data inicial (sem valores típicos - usa o valor detectado)
SEED_SERVICES = [
    # Streaming
    {
        "name": "Netflix",
        "patterns": ["NETFLIX", "NETFLIX.COM", "NETFLIX*"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Spotify",
        "patterns": ["SPOTIFY", "SPOTIFY AB", "SPOTIFY*"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Amazon Prime",
        "patterns": ["AMAZON PRIME", "AMZN PRIME", "PRIME VIDEO", "AMAZON*PRIME", "PRIME CANAIS"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Amazon Prime Ads Free",
        "patterns": ["AMAZON AD FREE", "AD FREE FOR PRI"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Disney+",
        "patterns": ["DISNEY+", "DISNEY PLUS", "DISNEYPLUS", "DISNEY*"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "HBO Max",
        "patterns": ["HBO MAX", "HBOMAX", "HBO*", "MAX", "HELPHBOMAX", "HBOMAX.COM"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "YouTube Premium",
        "patterns": ["YOUTUBE PREMIUM", "YOUTUBEPREMIUM", "GOOGLE YOUTUBE", "YOUTUBE MEMBER"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Globoplay",
        "patterns": ["GLOBOPLAY", "GLOBO*PLAY", "GLOBO PLAY"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Paramount+",
        "patterns": ["PARAMOUNT+", "PARAMOUNT PLUS", "PARAMOUNTPLUS"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Crunchyroll",
        "patterns": ["CRUNCHYROLL", "CRUNCHY*", "EBN*CRUNCHYROLL"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    {
        "name": "Deezer",
        "patterns": ["DEEZER", "DEEZER*"],
        "default_category": "streaming",
        "default_frequency": "monthly",
    },
    # Cloud & Software
    {
        "name": "Apple Services",
        "patterns": ["APPLE.COM/BILL", "APPLE COM BILL", "ITUNES", "APPLE*"],
        "default_category": "assinatura",
        "default_frequency": "monthly",
    },
    {
        "name": "Google One",
        "patterns": ["GOOGLE ONE"],
        "default_category": "cloud",
        "default_frequency": "monthly",
    },
    {
        "name": "Microsoft 365",
        "patterns": ["MICROSOFT", "PPRO*MICROSOFT", "MSONLINE"],
        "default_category": "software",
        "default_frequency": "monthly",
    },
    {
        "name": "ChatGPT Plus",
        "patterns": ["OPENAI", "CHATGPT", "OPENAI*"],
        "default_category": "software",
        "default_frequency": "monthly",
    },
    {
        "name": "Claude AI",
        "patterns": ["CLAUDE.AI", "CLAUDE AI"],
        "default_category": "tecnologia",
        "default_frequency": "monthly",
    },
    {
        "name": "Canva Pro",
        "patterns": ["CANVA", "CANVA*"],
        "default_category": "software",
        "default_frequency": "monthly",
    },
    {
        "name": "Dropbox",
        "patterns": ["DROPBOX", "DROPBOX*"],
        "default_category": "cloud",
        "default_frequency": "monthly",
    },
    {
        "name": "Adobe Creative Cloud",
        "patterns": ["ADOBE", "EBN *ADOBE", "ADOBE CREATIVE"],
        "default_category": "software",
        "default_frequency": "monthly",
    },
    {
        "name": "GitHub",
        "patterns": ["GITHUB", "GITHUB, INC"],
        "default_category": "tecnologia",
        "default_frequency": "monthly",
    },
    {
        "name": "JetBrains",
        "patterns": ["JETBRAINS", "JETBRAINS AMERICAS"],
        "default_category": "tecnologia",
        "default_frequency": "monthly",
    },
    {
        "name": "OpenRouter",
        "patterns": ["OPENROUTER"],
        "default_category": "tecnologia",
        "default_frequency": "monthly",
    },
    # Assinaturas de serviços
    {
        "name": "Mercado Livre Melius",
        "patterns": ["MERCADOLIVRE*MELIUS", "MELIUS", "MELI*MELIUS", "MERCADO*MELIUS"],
        "default_category": "assinaturas",
        "default_frequency": "monthly",
    },
    {
        "name": "iFood Club",
        "patterns": ["IFOOD CLUB", "IFOODCLUB"],
        "default_category": "alimentacao",
        "default_frequency": "monthly",
    },
    {
        "name": "Rappi Prime",
        "patterns": ["RAPPI*PRIME", "RAPPIPRIME", "RAPPI PRIME"],
        "default_category": "assinaturas",
        "default_frequency": "monthly",
    },
    {
        "name": "Uber One",
        "patterns": ["UBER*ONE", "UBER ONE", "UBERONE"],
        "default_category": "assinaturas",
        "default_frequency": "monthly",
    },
    {
        "name": "Wellhub/Gympass",
        "patterns": ["WELLHUB", "GYMPASS"],
        "default_category": "saude",
        "default_frequency": "monthly",
    },
    {
        "name": "Smiles",
        "patterns": ["SMILES", "CLUBE SMILES"],
        "default_category": "viagem",
        "default_frequency": "monthly",
    },
    {
        "name": "Livelo",
        "patterns": ["LIVELO", "CLUBE LIVELO"],
        "default_category": "assinatura",
        "default_frequency": "monthly",
    },
    {
        "name": "Starlink",
        "patterns": ["STARLINK", "DL *STARLINK"],
        "default_category": "servicos",
        "default_frequency": "monthly",
    },
    # Games
    {
        "name": "PlayStation Plus",
        "patterns": ["PLAYSTATION", "PSN*", "SONY ENTERTAINMENT"],
        "default_category": "jogos",
        "default_frequency": "monthly",
    },
    {
        "name": "Xbox Game Pass",
        "patterns": ["XBOX", "MICROSOFT*XBOX", "GAMEPASS"],
        "default_category": "jogos",
        "default_frequency": "monthly",
    },
    # Saúde e Fitness
    {
        "name": "Strava",
        "patterns": ["STRAVA", "STRAVA*"],
        "default_category": "saude",
        "default_frequency": "monthly",
    },
]


def upgrade():
    # Criar tabela known_recurring_services
    op.create_table(
        "known_recurring_services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("patterns", JSON, nullable=False),
        sa.Column("default_category", sa.String(50), nullable=True),
        sa.Column("default_frequency", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_known_recurring_services_name", "known_recurring_services", ["name"])

    # Inserir seed data
    known_services_table = sa.table(
        "known_recurring_services",
        sa.column("name", sa.String),
        sa.column("patterns", JSON),
        sa.column("default_category", sa.String),
        sa.column("default_frequency", sa.String),
    )

    op.bulk_insert(known_services_table, SEED_SERVICES)


def downgrade():
    op.drop_index("ix_known_recurring_services_name", "known_recurring_services")
    op.drop_table("known_recurring_services")
