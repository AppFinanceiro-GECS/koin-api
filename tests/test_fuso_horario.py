import pytest
from freezegun import freeze_time
from app.core.utils import today_br
from datetime import date

# Congela o relógio UTC exatamente em 02:30 do dia 16.
# Isso equivale a 23:30 do dia 15 no fuso de Brasília.
@freeze_time("2026-10-16 02:30:00", tz_offset=0)
def test_transacao_as_23h30_de_brasilia_mantem_data_local_correta():
    # Valida se a função que nós criamos compensa o fuso
    assert today_br() == date(2026, 10, 15)