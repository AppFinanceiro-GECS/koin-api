# Retenção e proteção das faturas enviadas

Base para a política de privacidade do Koin e para o pedido da LGPD de guardar o mínimo pelo menor tempo. A fatura de cartão é dado financeiro pessoal.

## O que é guardado e por quanto tempo

| Dado | Quando é apagado |
|---|---|
| Arquivo original (PDF ou foto) | **30 dias** depois do processamento, se a fatura já foi confirmada (virou transação, fatura ou compra) |
| Dados extraídos pela IA (`extracted_data`, a lista de compras lida) | Junto com o arquivo original |
| Arquivo de envio que falhou | 30 dias depois do envio |
| Envio ainda não confirmado, na fila da IA ou em processamento | Não é apagado automaticamente: a pessoa ainda pode confirmar |
| Transações confirmadas | Ficam na conta até a pessoa excluí-las ou excluir a conta |
| Conta excluída | Desativada na hora; os dados seguem o processo de exclusão de conta (#47) |

- O prazo vem de `DOCUMENT_RETENTION_DAYS` (padrão 30; `0` desliga).
- O job `purge_expired_documents` roda todo dia às 03:30.
- Depois da limpeza, a linha do documento continua com o hash (para detectar reenvio) e com o vínculo com as transações. O arquivo e os dados extraídos deixam de existir.
- Reprocessar um documento já limpo responde `410 file_missing`.

A pessoa que quiser apagar antes pode excluir o documento no app (`DELETE /documents/{id}`), o que remove o arquivo na hora.

## Criptografia

- **Em trânsito:** HTTPS com certificado Let's Encrypt, pelo Caddy.
- **Banco e arquivos em repouso:** os volumes da VM na Oracle Cloud são criptografados por padrão (AES-256, chaves gerenciadas pela Oracle). Isso vale para o banco Postgres e para a pasta de uploads.
- **Senha de PDF salva no cartão:** criptografada na aplicação (`app/core/crypto.py`) e nunca registrada em log.
- **Object storage** (#25): quando os uploads saírem do disco da VM, o bucket terá criptografia no servidor (SSE) e acesso privado.

## Subprocessadores

| Serviço | Para que | Dados que recebe |
|---|---|---|
| Google (Gemini API) | Ler a fatura enviada | O conteúdo do arquivo, no momento da leitura. Em produção, só com chave do **tier pago**, em que o Google não usa o conteúdo para treinar (#21) |
| Mistral AI (opcional, se configurado) | Leitura alternativa de faturas | O conteúdo do arquivo, no momento da leitura |
| Oracle Cloud (São Paulo) | Hospedagem da API, do banco e dos arquivos | Todos os dados da conta |
| Provedor de e-mail (#22; hoje Gmail na homologação) | Convite, redefinição de senha e avisos | Nome e e-mail |
| Expo (push, quando ativado no #43) | Notificações no celular | Token do aparelho e o texto do aviso |
