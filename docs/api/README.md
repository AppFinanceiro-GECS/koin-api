# Testar a API à mão

## Coleção Bruno

A pasta `koin/` é uma coleção do [Bruno](https://www.usebruno.com/), um cliente HTTP gratuito que guarda as requisições como arquivos no repositório.

1. Instale o Bruno e abra a pasta `docs/api/koin` (*Open Collection*).
2. Escolha o ambiente `hml` ou `local` e preencha `email` e `password`. A senha fica como segredo do Bruno e não vai para o Git.
3. Rode em ordem, de **01 Health** a **16 Logout**. O login guarda o token, e as requisições seguintes guardam os ids que as próximas usam: conta, cartão, transação, fatura e documento.

Notas:
- O access token vale 15 minutos. Quando expirar, rode **03 Refresh**.
- **12 Enviar fatura** usa a fatura sintética `tests/fixtures/documents/nubank.pdf` e gasta cota da IA da homologação.
- Sem conta na hml? Peça um convite ao admin. O link e o token vêm na resposta do convite.
- Para ter dados sem montar tudo à mão, use o usuário demo: `make seed-hml`.

O mesmo fluxo roda no CI depois de cada deploy da hml (job *Smoke E2E*, `scripts/smoke_e2e.py`).

## Roteiro exploratório

O [ROTEIRO-HML.md](ROTEIRO-HML.md) lista o que conferir à mão depois de uma mudança grande, com o resultado esperado de cada caso.
