# Checklist de Segurança e Remediação — Biveto App

Este documento reúne recomendações práticas para identificar e remediar exposições de segredos, chaves, certificados e dados sensíveis detectadas no repositório.

IMPORTANTE: a busca automática pode estar incompleta. Verifique o histórico do Git e execute scanners adicionais (gitleaks, truffleHog, detect-secrets). Link do repositório: https://github.com/kalebeasilvadev/biveto-app

---

## 1) Ações imediatas (faça agora)

1. Rotacionar credenciais comprometidas
   - Revogar e substituir imediatamente qualquer credencial que possa ter sido exposta: certificados/TLS, chaves privadas, senhas de banco, tokens de API, JWT SECRET.
   - Geração de secret JWT seguro:
     - python -c "import secrets; print(secrets.token_urlsafe(64))"

2. Remover arquivos sensíveis do repo (local + remoto)
   - Remover os arquivos a seguir do repositório e do histórico:
     - frontend/certs.bak/key.pem
     - frontend/certs.bak/cert.pem
     - frontend/public/certs/cert.pem
   - Ferramentas recomendadas para reescrever histórico:
     - git-filter-repo (recomendado):
       - git clone --mirror git@github.com:kalebeasilvadev/biveto-app.git
       - cd biveto-app.git
       - git filter-repo --path frontend/certs.bak/key.pem --path frontend/certs.bak/cert.pem --path frontend/public/certs/cert.pem --replace-refs delete
       - git push --force
     - BFG Repo-Cleaner (alternativa):
       - java -jar bfg.jar --delete-files cert.pem,key.pem --no-blob-protection
       - git reflog expire --expire=now --all && git gc --prune=now --aggressive
       - git push --force
   - Antes de forçar push: comunicar a equipe — reescrever histórico exige coordenação (todos precisam reclonar/pull --rebase/force).

3. Trocar senhas usadas em serviços que podem ter sido comprometidos
   - Postgres: alterar senha se o banco estiver acessível com `POSTGRES_PASSWORD=biveto_secret`.
   - Outras integrações (Google API, OpenAI, Mistral, SMTP): rotacionar chaves se houver risco.

4. Isolar e proteger dados sensíveis que estiverem em arquivos (PDFs, testes)
   - Apagar ou mover PDFs com dados reais para local seguro (tests/fixtures com dados sintetizados ou fixtures anonimizadas).

5. Bloquear novos commits com segredos
   - Habilitar política de branch protegida e impedir force-push da branch principal até mitigar.

---

## 2) Limpeza e prevenção (curto prazo — 1-7 dias)

1. Adicionar/atualizar .gitignore
   - Exemplos de entradas:
     - /frontend/certs.bak/
     - /frontend/public/certs/
     - *.pem
     - *.key
     - .env
     - .env.*
     - /uploads/
     - /private/

2. Adicionar hooks pre-commit para bloquear segredos locais
   - Usar pre-commit com detect-secrets / gitleaks:
     - pip install pre-commit
     - pre-commit install
     - Adicionar .pre-commit-config.yaml com detect-secrets/gitleaks

3. Escanear histórico e gerar relatório
   - Ferramentas sugeridas:
     - gitleaks: `gitleaks detect --source . --report=gitleaks-report.json`
     - truffleHog: `trufflehog git https://github.com/kalebeasilvadev/biveto-app` 
     - detect-secrets: `detect-secrets scan --all-files > .secrets.baseline`
   - Revisar e mitigar todos os achados (rotacionar chaves conforme necessário).

4. Revisar GitHub Actions / CI
   - Verificar workflows em .github/workflows por segredos hard-coded.
   - Garantir que secrets do GitHub Actions sejam usados via `${{ secrets.NAME }}` e não comitados.

5. Remover dados sensíveis dos arquivos de configuração
   - Substituir valores hard-coded (ex: `POSTGRES_PASSWORD=biveto_secret`) por variáveis de ambiente e dar instruções no .env.example apenas com placeholders.

6. Re-emissão de certificados
   - Revogar e emitir novo certificado/TLS se a chave privada tiver sido exposta.
   - Atualizar servidores com novo par cert+key e testar.

---

## 3) Fortalecimento (médio prazo — 1-4 semanas)

1. Mover secrets para secret managers
   - AWS Secrets Manager, Google Secret Manager, HashiCorp Vault, Fly.io secrets, GitHub Secrets.
   - Documentar onde cada secret é armazenado e quem tem acesso.

2. Melhorar criptografia de dados
   - Crypto.py atualmente deriva chave Fernet de settings.secret_key — tratar secret_key como altamente sensível e rotacionável.
   - Considerar usar uma chave de criptografia separada (KMS/secret manager) em vez de derivar de secret_key.

3. Implementar rotação automática e monitoramento
   - Rotacionar chaves periodicamente e ter playbook de resposta a incidentes.
   - Ativar alertas de uso incomum (uso de API Keys, picos de tráfego, IPs desconhecidos).

4. Política de gestão de chaves e controle de acesso
   - Minimizar quem pode criar/visualizar secrets.
   - Usar RBAC e principio do menor privilégio.

5. Revisão de permissões e logs
   - Audit logs para operações sensíveis (criação/revogação de keys, mudanças de senha).

---

## 4) Procedimentos pós-incidente (comunicação e compliance)

1. Registre o incidente
   - Datas, arquivos afetados, ações tomadas (rotacionamento, commits, push force), chaves rotacionadas.

2. Notifique stakeholders
   - Equipe interna, proprietários dos serviços, se aplicável clientes ou autoridade (se PII vazou conforme legislação).

3. Verificação e testes
   - Validar que sistemas não aceitam mais as credenciais antigas.
   - Testar fluxos críticos (login, upload, envio de email) após mudanças.

---

## 5) Comandos e exemplos úteis

- Gerar SECRET_KEY forte:
  - python -c "import secrets; print(secrets.token_urlsafe(64))"

- Remover arquivos com git-filter-repo (exemplo):
  - git clone --mirror git@github.com:kalebeasilvadev/biveto-app.git
  - cd biveto-app.git
  - git filter-repo --path frontend/certs.bak/key.pem --path frontend/certs.bak/cert.pem --path frontend/public/certs/cert.pem --replace-refs delete
  - git push --force

- Usar gitleaks:
  - gitleaks detect --source . --report=gitleaks-report.json

- Pré-commit básico (.pre-commit-config.yaml):
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.0.3
    hooks:
      - id: detect-secrets

---

## 6) Checklist resumido (marcar quando feito)

- [ ] Rotacionar / revogar certificados e chaves expostas
- [ ] Alterar senha do Postgres se estiver em uso real
- [ ] Gerar e aplicar novo SECRET_KEY em produção
- [ ] Remover arquivos sensíveis do repositório e reescrever histórico
- [ ] Adicionar .gitignore apropriado
- [ ] Instalar e configurar pre-commit hooks (detect-secrets/gitleaks)
- [ ] Rodar gitleaks/truffleHog/detect-secrets no histórico e remediar achados
- [ ] Remover PDFs e dados PII do repositório ou anonimizar
- [ ] Verificar e corrigir workflows do CI (nenhum segredo commited)
- [ ] Mover secrets para secret manager e documentar
- [ ] Implementar monitoramento e alertas para uso de keys
- [ ] Comunicar incidentes e documentar ações realizadas

---

Se quiser, eu posso:
- 1) Criar um PR sugerindo .gitignore e .pre-commit-config.yaml
- 2) Rodar uma varredura adicional no histórico (usando buscas de código/commits) e gerar relatório com arquivos encontrados
- 3) Gerar instruções passo-a-passo para reescrever histórico e coordenar o force-push

Diga qual ação prefere que eu faça a seguir.
