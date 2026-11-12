"""
Divisão das despesas da casa: quem pagou o quê e quem deve a quem.

Entram as despesas marcadas como da família (ownership_type = household) que os membros
lançaram no mês. Cada membro tem uma parte (igual entre todos, ou a porcentagem definida
pelo dono da família, por exemplo proporcional à renda). O saldo de cada um é o que pagou
menos a sua parte, já descontados os acertos registrados. As transferências sugeridas
quitam os saldos com o menor número de Pix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.household import HouseholdMember, HouseholdSettlement
from app.models.transaction import Transaction
from app.models.user import User

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


@dataclass
class MemberSplit:
    member_id: int
    user_id: int
    name: str
    share_percent: Decimal
    paid: Decimal = CENT * 0
    expenses_count: int = 0
    fair_share: Decimal = CENT * 0
    settled_out: Decimal = CENT * 0  # acertos que este membro pagou
    settled_in: Decimal = CENT * 0  # acertos que este membro recebeu
    balance: Decimal = CENT * 0  # > 0: tem a receber; < 0: tem a pagar


@dataclass
class Transfer:
    from_user_id: int
    from_name: str
    to_user_id: int
    to_name: str
    amount: Decimal


@dataclass
class CategoryTotal:
    name: str
    amount: Decimal


@dataclass
class SettlementItem:
    id: int
    from_user_id: int
    to_user_id: int
    amount: Decimal
    note: str | None
    created_at: object


@dataclass
class FamilySplit:
    year: int
    month: int
    total: Decimal
    split_mode: str  # equal | custom
    members: list[MemberSplit]
    transfers: list[Transfer]
    categories: list[CategoryTotal] = field(default_factory=list)
    settlements: list[SettlementItem] = field(default_factory=list)

    @property
    def is_settled(self) -> bool:
        return not self.transfers


def member_name(member: HouseholdMember, user: User | None) -> str:
    if member.nickname:
        return member.nickname
    if user and user.name:
        return user.name.split()[0]
    return user.email.split("@")[0] if user else "Membro"


def resolve_shares(members: list[HouseholdMember]) -> tuple[dict[int, Decimal], str]:
    """Parte de cada membro em %. Só usa as definidas se todos tiverem e somarem 100"""
    custom = [m.share_percent for m in members]
    if members and all(p is not None for p in custom):
        total = sum(Decimal(str(p)) for p in custom)
        if abs(total - HUNDRED) <= CENT:
            return {m.id: Decimal(str(m.share_percent)) for m in members}, "custom"
    if not members:
        return {}, "equal"
    equal = HUNDRED / len(members)
    return {m.id: equal for m in members}, "equal"


def _distribute(total: Decimal, weights: dict[int, Decimal]) -> dict[int, Decimal]:
    """Reparte o total em centavos pela porcentagem; a sobra de arredondamento vai para o maior"""
    if not weights:
        return {}
    shares = {
        k: (total * w / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP) for k, w in weights.items()
    }
    diff = total - sum(shares.values())
    if diff:
        biggest = max(weights, key=lambda k: (weights[k], -k))
        shares[biggest] += diff
    return shares


def suggest_transfers(members: list[MemberSplit]) -> list[Transfer]:
    """Quita os saldos com o menor número de transferências (guloso, maior com maior)"""
    debtors = [[m, -m.balance] for m in members if m.balance <= -CENT]
    creditors = [[m, m.balance] for m in members if m.balance >= CENT]
    debtors.sort(key=lambda x: (-x[1], x[0].user_id))
    creditors.sort(key=lambda x: (-x[1], x[0].user_id))
    transfers: list[Transfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor, owes = debtors[i]
        creditor, due = creditors[j]
        amount = min(owes, due)
        if amount >= CENT:
            transfers.append(
                Transfer(
                    from_user_id=debtor.user_id,
                    from_name=debtor.name,
                    to_user_id=creditor.user_id,
                    to_name=creditor.name,
                    amount=amount,
                )
            )
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] < CENT:
            i += 1
        if creditors[j][1] < CENT:
            j += 1
    return transfers


async def build_family_split(
    db: AsyncSession, license_id: int, year: int, month: int
) -> FamilySplit:
    members = list(
        (
            await db.execute(
                select(HouseholdMember)
                .where(HouseholdMember.license_id == license_id)
                .order_by(HouseholdMember.joined_at, HouseholdMember.id)
            )
        )
        .scalars()
        .all()
    )
    user_ids = [m.user_id for m in members]
    users = (
        {
            u.id: u
            for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        }
        if user_ids
        else {}
    )

    weights, mode = resolve_shares(members)
    splits = {
        m.user_id: MemberSplit(
            member_id=m.id,
            user_id=m.user_id,
            name=member_name(m, users.get(m.user_id)),
            share_percent=weights.get(m.id, Decimal(0)).quantize(CENT),
        )
        for m in members
    }

    start, end = month_range(year, month)
    shared = (
        Transaction.user_id.in_(user_ids),
        Transaction.ownership_type == "household",
        Transaction.type == "expense",
        Transaction.date >= start,
        Transaction.date < end,
    )
    if user_ids:
        rows = await db.execute(
            select(Transaction.user_id, func.sum(Transaction.amount), func.count(Transaction.id))
            .where(*shared)
            .group_by(Transaction.user_id)
        )
        for user_id, amount, count in rows.all():
            splits[user_id].paid = _money(amount)
            splits[user_id].expenses_count = int(count)

        cat_rows = await db.execute(
            select(func.coalesce(Category.name, "Sem categoria"), func.sum(Transaction.amount))
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .where(*shared)
            .group_by(Category.name)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(5)
        )
        categories = [CategoryTotal(name=n, amount=_money(a)) for n, a in cat_rows.all()]
    else:
        categories = []

    total = sum((s.paid for s in splits.values()), Decimal(0)).quantize(CENT)
    fair = _distribute(total, {m.user_id: weights[m.id] for m in members})
    for user_id, value in fair.items():
        splits[user_id].fair_share = value

    settlements = list(
        (
            await db.execute(
                select(HouseholdSettlement)
                .where(
                    HouseholdSettlement.license_id == license_id,
                    HouseholdSettlement.year == year,
                    HouseholdSettlement.month == month,
                )
                .order_by(HouseholdSettlement.created_at, HouseholdSettlement.id)
            )
        )
        .scalars()
        .all()
    )
    for s in settlements:
        amount = _money(s.amount)
        if s.from_user_id in splits:
            splits[s.from_user_id].settled_out += amount
        if s.to_user_id in splits:
            splits[s.to_user_id].settled_in += amount

    for split in splits.values():
        # pagar um acerto conta como ter pago a casa; receber, como devolver
        split.balance = split.paid + split.settled_out - split.settled_in - split.fair_share

    ordered = [splits[m.user_id] for m in members]
    return FamilySplit(
        year=year,
        month=month,
        total=total,
        split_mode=mode,
        members=ordered,
        transfers=suggest_transfers(ordered),
        categories=categories,
        settlements=[
            SettlementItem(
                id=s.id,
                from_user_id=s.from_user_id,
                to_user_id=s.to_user_id,
                amount=_money(s.amount),
                note=s.note,
                created_at=s.created_at,
            )
            for s in settlements
        ],
    )
