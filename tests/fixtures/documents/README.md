# Fixtures sintéticas de extração

Todos os documentos foram desenhados do zero. Nomes, estabelecimentos, valores,
datas e final de cartão são inventados. Não há CPF, endereço, cartão completo,
fatura histórica ou documento pessoal. Os nomes dos bancos apenas ativam os
prompts atuais; cada página está identificada como sintética e sem validade.

| Documento | Cenário | Itens esperados | Total |
|---|---|---:|---:|
| `itau_two_columns.pdf` | Duas páginas; duas colunas de lançamentos na segunda; próximas parcelas excluídas | 4 | R$ 280,00 |
| `nubank.pdf` | Datas DD MMM, virada do ano, parcela, IOF e pagamento anterior excluído | 4 | R$ 150,00 |
| `bradesco.pdf` | Resumo separado, tabela com cidade, parcela concatenada, crédito com hífen final e pagamento excluído | 4 | R$ 160,00 |
| `cupom_fiscal.png` | Quatro produtos, incluindo sacola de baixo valor e pagamento separado | 4 | R$ 32,00 |

Os JSONs `.expected.json` contêm `document_type`, `total_amount` e `items`.
Cada item tem `description` e `amount`; datas e parcelas são exigidas somente
quando relevantes ao cenário. Não são snapshots de confidence, categorias,
metadados pessoais ou toda a resposta da IA. Totais são constantes conhecidas
no documento, nunca calculadas a partir da resposta extraída.

Regeneração local, somente com dependências já declaradas:

```sh
python tests/fixtures/documents/generate.py
```

O benchmark usa o serviço real Google, parser e validator atuais. A tolerância
de produção de R$ 50 não é usada: valores e totais são comparados em centavos,
com itens tratados como um multiconjunto, sem depender da ordem.

```sh
python -m pytest
python -m pytest -m "not live"
# Futuramente, com GOOGLE_API_KEY no ambiente ou .env:
python -m pytest tests/test_document_extraction_live.py -m live --run-live
```

Sem `--run-live`, todos os testes live são skipped, inclusive com `-m live`.
Não há bloqueio global de rede nos testes comuns. A proteção deste benchmark
usa o marker, o opt-in explícito e o filtro `-m "not live"` do CI.
Sem chave Google ou SDK, os casos também são skipped. Um benchmark com todos
os casos skipped não foi executado e não é um benchmark concluído.
São oito combinações: quatro documentos
com `gemini-3.8-flash` e `gemini-3.5-flash-lite`. Nenhum default é modificado.
O teste desabilita temporariamente a chave Mistral e impede sua construção.
Cada tentativa registra `pass`, `quality_failure` ou `technical_error`.
`pass` significa que itens, valores, totais e demais campos esperados correspondem.
`quality_failure` significa que a extração foi tecnicamente concluída com resposta
processável, mas seu conteúdo diverge do JSON esperado. `technical_error` significa
que um problema técnico impediu avaliar a qualidade da extração. Erros
técnicos fazem o teste falhar com mensagem sanitizada, sem comparação de itens,
e não entram no denominador de qualidade. Erros retornados pelo próprio serviço
também são técnicos, mesmo quando ele captura a exceção internamente.

Por modelo, `completed_cases = passed_cases + quality_failures`, e
`case_accuracy = passed_cases / completed_cases`. Sem casos concluídos, a
acurácia é `N/A`. Itens e totais agregam somente casos concluídos. A duração
mostra separadamente o total de tentativas e o total/média de casos concluídos;
inclui preparação local, isolamento do provider, extração e retries.

O relatório mostra a matriz esperada de 8 casos, os selecionados, registrados,
skipped e não registrados, sinalizando `INCOMPLETE` para uma matriz parcial.
`matrix=complete` significa que as 8 tentativas foram registradas, não que todas
foram processadas com sucesso: verifique também `technical_errors` e os skips.
Uma seleção parcial ou execução interrompida não conclui o benchmark completo.
Retries do provider podem gerar mais de 8 requisições externas.
Não há limite rígido de latência nem decisão automática sobre modelo ou alias.
