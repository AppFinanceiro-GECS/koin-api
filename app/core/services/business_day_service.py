"""
Serviço para cálculo de dias úteis no Brasil.
Considera feriados nacionais fixos e móveis.
"""

from datetime import date, timedelta


def get_brazilian_holidays(year: int) -> list[date]:
    """
    Retorna lista de feriados nacionais brasileiros para um ano.
    Inclui feriados fixos e móveis (Páscoa, Carnaval, Corpus Christi).
    """
    holidays = []

    # Feriados fixos
    fixed_holidays = [
        (1, 1),  # Ano Novo
        (4, 21),  # Tiradentes
        (5, 1),  # Dia do Trabalho
        (9, 7),  # Independência
        (10, 12),  # Nossa Senhora Aparecida
        (11, 2),  # Finados
        (11, 15),  # Proclamação da República
        (12, 25),  # Natal
    ]

    for month, day in fixed_holidays:
        holidays.append(date(year, month, day))

    # Páscoa (algoritmo de Gauss)
    easter = calculate_easter(year)
    holidays.append(easter)

    # Sexta-feira Santa (2 dias antes da Páscoa)
    good_friday = easter - timedelta(days=2)
    holidays.append(good_friday)

    # Carnaval (47 dias antes da Páscoa - terça-feira)
    carnival_tuesday = easter - timedelta(days=47)
    holidays.append(carnival_tuesday)

    # Segunda-feira de Carnaval
    carnival_monday = easter - timedelta(days=48)
    holidays.append(carnival_monday)

    # Corpus Christi (60 dias após a Páscoa)
    corpus_christi = easter + timedelta(days=60)
    holidays.append(corpus_christi)

    return sorted(holidays)


def calculate_easter(year: int) -> date:
    """
    Calcula a data da Páscoa usando o algoritmo de Gauss.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def is_business_day(check_date: date, holidays: list[date] | None = None) -> bool:
    """
    Verifica se uma data é dia útil (não é fim de semana nem feriado).
    """
    # Fim de semana
    if check_date.weekday() >= 5:  # 5 = sábado, 6 = domingo
        return False

    # Feriado
    if holidays is None:
        holidays = get_brazilian_holidays(check_date.year)

    if check_date in holidays:
        return False

    return True


def get_nth_business_day(year: int, month: int, n: int) -> date:
    """
    Retorna o N-ésimo dia útil de um mês.

    Args:
        year: Ano
        month: Mês (1-12)
        n: Qual dia útil (1 para primeiro, 5 para quinto, etc.)

    Returns:
        Data do N-ésimo dia útil do mês

    Raises:
        ValueError: Se n for inválido ou não houver dias úteis suficientes no mês
    """
    if n < 1:
        raise ValueError("n deve ser >= 1")

    # Obter feriados do ano (e do próximo, caso o mês seja dezembro)
    holidays = get_brazilian_holidays(year)
    if month == 12:
        holidays.extend(get_brazilian_holidays(year + 1))

    # Começar do primeiro dia do mês
    current_date = date(year, month, 1)
    business_day_count = 0

    # Encontrar o próximo mês para saber quando parar
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    while current_date < next_month_start:
        if is_business_day(current_date, holidays):
            business_day_count += 1
            if business_day_count == n:
                return current_date
        current_date += timedelta(days=1)

    raise ValueError(f"O mês {month}/{year} não tem {n} dias úteis")


def get_payment_date_for_income(
    year: int,
    month: int,
    payment_day: int | None = None,
    use_business_day: bool = False,
    business_day_number: int | None = None,
) -> date:
    """
    Calcula a data de pagamento para uma fonte de receita.

    Args:
        year: Ano do pagamento
        month: Mês do pagamento
        payment_day: Dia fixo do mês (1-31), usado se use_business_day=False
        use_business_day: Se True, usa dia útil ao invés de dia fixo
        business_day_number: Qual dia útil (ex: 5 para 5º dia útil)

    Returns:
        Data do pagamento
    """
    if use_business_day and business_day_number:
        return get_nth_business_day(year, month, business_day_number)
    elif payment_day:
        # Ajustar para o último dia do mês se necessário
        from calendar import monthrange

        last_day = monthrange(year, month)[1]
        day = min(payment_day, last_day)
        return date(year, month, day)
    else:
        # Default: primeiro dia do mês
        return date(year, month, 1)


def get_next_payment_date(
    payment_day: int | None = None,
    use_business_day: bool = False,
    business_day_number: int | None = None,
    reference_date: date | None = None,
) -> date:
    """
    Calcula a próxima data de pagamento a partir de uma data de referência.

    Args:
        payment_day: Dia fixo do mês
        use_business_day: Se True, usa dia útil
        business_day_number: Qual dia útil
        reference_date: Data de referência (default: hoje)

    Returns:
        Próxima data de pagamento
    """
    if reference_date is None:
        reference_date = date.today()

    # Calcular para o mês atual
    payment_date = get_payment_date_for_income(
        reference_date.year,
        reference_date.month,
        payment_day,
        use_business_day,
        business_day_number,
    )

    # Se a data já passou, calcular para o próximo mês
    if payment_date <= reference_date:
        if reference_date.month == 12:
            payment_date = get_payment_date_for_income(
                reference_date.year + 1, 1, payment_day, use_business_day, business_day_number
            )
        else:
            payment_date = get_payment_date_for_income(
                reference_date.year,
                reference_date.month + 1,
                payment_day,
                use_business_day,
                business_day_number,
            )

    return payment_date
