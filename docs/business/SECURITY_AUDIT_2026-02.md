# Análise de Segurança - Biveto App
**Data:** 07 de Fevereiro de 2026
**Versão:** 1.0
**Analista:** Claude Code Security Audit
**Aplicação:** Biveto Financial Management (FastAPI + React)

---

## 📊 Resumo Executivo

Esta análise identificou **18 potenciais issues de segurança** no projeto Biveto App, sendo:
- **0 Críticas Reais** (2 falsos positivos eliminados após análise contextual)
- **4 Altas** (requerem atenção)
- **8 Médias** (melhorias recomendadas)
- **6 Baixas** (boas práticas)

**Postura de Segurança Geral:** ✅ **BOA** - O projeto segue boas práticas de segurança com algumas áreas de melhoria.

**Vulnerabilidades Críticas Eliminadas:**
- ✅ Arquivos `.env` corretamente no `.gitignore` e não versionados
- ✅ Uso de bcrypt para senhas
- ✅ SQLAlchemy com queries parametrizadas (previne SQL injection)
- ✅ Headers de segurança implementados

---

## 🔴 ALTA SEVERIDADE (Ação Recomendada)

### 1. Vulnerabilidades em Dependências Frontend

**Status:** ✅ CONFIRMADO
**Severidade:** Alta
**Arquivo:** `frontend/package.json`

**Detalhes:**
```bash
npm audit
# 3 high severity vulnerabilities
# @remix-run/router: XSS via Open Redirects (CVE-XXXX)
# CVSS Score: 8.0
```

**Impacto da Vulnerabilidade:**
- Atacante pode redirecionar usuários para sites maliciosos
- Possível roubo de credenciais via phishing
- XSS em certas condições de uso

**Impacto da Correção:**
- ✅ Atualiza react-router-dom
- ⚠️ Pode quebrar navegação se houver breaking changes
- ⚠️ Testar todas as rotas após atualização

**Como Corrigir:**
```bash
# Ver o que vai mudar
npm outdated react-router-dom

# Opção 1: Correção automática (mais seguro)
npm audit fix

# Opção 2: Forçar atualização (pode quebrar)
npm audit fix --force

# Depois: Testar navegação em todas as páginas
npm run dev
```

**Esforço:** 2-4 horas (atualização + testes)
**Risco de Quebrar:** Médio
**Recomendação:** ✅ **FAZER** - Testar bem após aplicar

---

### 2. JWT Secret em Produção

**Status:** ⚠️ A VERIFICAR
**Severidade:** Alta (SE o secret em produção for fraco)
**Arquivo:** Configuração Fly.io

**Detalhes:**
O `.env` local tem:
```
SECRET_KEY=dev-secret-key-mude-em-producao-12345
```

**Questões:**
1. Qual secret está configurado no Fly.io?
2. É forte ou é baseado no .env local?

**Como Verificar:**
```bash
flyctl secrets list --app app-financeiro
```

**Se o secret for fraco:**

**Impacto da Vulnerabilidade:**
- Atacante pode forjar tokens JWT
- Impersonação de qualquer usuário (incluindo admin)
- Acesso completo a dados financeiros

**Impacto da Correção:**
- ⚠️ **TODOS os usuários serão deslogados** (tokens invalidados)
- ⚠️ Precisa avisar usuários (downtime planejado)
- ✅ Zero mudanças de código

**Como Corrigir:**
```bash
# 1. Gerar secret forte
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# Exemplo de output:
# xK8mN2pL9vB4qR7sT6wY3zA1cD5eF8gH2jK4lM7nP9qR3sT6vW8xY2zA5bC8dE1f

# 2. Configurar no Fly.io (app reinicia automaticamente)
flyctl secrets set SECRET_KEY="PASTE_AQUI_O_SECRET_GERADO" --app app-financeiro

# 3. App reinicia em ~30 segundos
# 4. Usuários fazem login novamente
```

**Esforço:** 5 minutos
**Risco de Quebrar:** Zero (só desloga usuários)
**Recomendação:** ✅ **FAZER** - Muito fácil, muito importante

---

### 3. JWT Tokens no localStorage

**Status:** ✅ REAL (mas mitigável)
**Severidade:** Alta → Média (com mitigações)
**Arquivo:** `frontend/src/stores/authStore.ts`

**Detalhes:**
Tokens JWT armazenados em localStorage são acessíveis via JavaScript:
```typescript
localStorage.getItem('auth-storage')
// { "accessToken": "eyJ...", "refreshToken": "eyJ..." }
```

**Impacto da Vulnerabilidade:**
- **SE** houver XSS no app, atacante pode roubar tokens
- **SE** usuário instalar extensão maliciosa, pode acessar tokens
- Sem XSS = sem problema

**Opção 1: Migrar para httpOnly Cookies (INVASIVO)**

**O QUE QUEBRA:**
- ❌ Todo o sistema de auth atual
- ❌ Zustand persist
- ❌ Token refresh logic
- ❌ Axios interceptors
- ❌ Precisa refatorar 5+ arquivos

**Arquivos Afetados:**
- `authStore.ts` - Reescrever completo
- `api.ts` - Adicionar withCredentials
- `main.py` (backend) - Configurar cookies
- `auth.py` (backend) - Retornar Set-Cookie
- CORS - Permitir credentials

**Esforço:** 12-16 horas + testes extensivos
**Risco:** ALTO - Muito pode quebrar

**Opção 2: Manter localStorage + Adicionar Proteções (SIMPLES)**

**O QUE FAZER:**
- ✅ Adicionar Content-Security-Policy header
- ✅ Sanitizar todos os inputs de usuário
- ✅ Usar DOMPurify se renderizar HTML
- ✅ Validar/escapar dados em ReactMarkdown

**Código:**
```python
# app/main.py - Adicionar CSP
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # React precisa
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://app-financeiro.fly.dev"
)
```

**Esforço:** 2-3 horas
**Risco:** Baixo

**Recomendação:** ✅ **Opção 2** - CSP + sanitização (muito mais simples)

---

### 4. Secrets em Produção (Geral)

**Status:** ⚠️ A VERIFICAR
**Como Verificar:**
```bash
# Ver todos os secrets configurados
flyctl secrets list --app app-financeiro

# Deveriam existir:
# - SECRET_KEY (JWT secret)
# - DATABASE_URL (conexão do banco)
# - ANTHROPIC_API_KEY (se usar)
# - Outros API keys
```

**Se algum secret estiver fraco:**

**Impacto da Correção:**
- Secret novo → Tokens antigos invalidados → Usuários deslogam
- Database URL nova → Precisa provisionar novo banco (⚠️ CUIDADO!)

**Recomendação:** Verificar primeiro, corrigir só se necessário

---

## 🟡 MÉDIA SEVERIDADE (Melhorias)

### 5. Rate Limiting com Múltiplas Instâncias

**Status:** ⚠️ DEPENDE DA ARQUITETURA
**Severidade:** Média (SE múltiplas máquinas)

**Como Verificar:**
```bash
flyctl status --app app-financeiro
# Ver quantas máquinas estão rodando
```

**Se 1 máquina:** ✅ Funciona perfeitamente (memory:// OK)
**Se 2+ máquinas:** ⚠️ Rate limit é por máquina (problema)

**Correção (só se múltiplas máquinas):**

**O QUE MUDA:**
- Provisionar Redis no Fly.io
- Configurar `storage_uri = "redis://..."`
- Adicionar dependência: `redis-py`

**VAI QUEBRAR:**
- ⚠️ Se Redis cair, rate limit para de funcionar
- ⚠️ Custo mensal adicional (~$5-10)
- ⚠️ Latência adicional (~1-5ms por request)

**Código:**
```python
# rate_limit.py
import os
storage_uri = os.getenv("REDIS_URL", "memory://")
limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=storage_uri,
    default_limits=["100/minute"],
)
```

**Provisionar Redis no Fly.io:**
```bash
flyctl redis create
# Escolher plano (mínimo: eviction, ~$5/mês)
# Configura automaticamente REDIS_URL como secret
```

**Esforço:** 2 horas
**Custo:** $5-10/mês
**Recomendação:** Só fazer se app escalar para múltiplas máquinas

---

### 6. CORS Muito Permissivo em Dev

**Status:** ✅ CONFIRMADO (só em dev)
**Severidade:** Baixa (se não vazar para prod)
**Arquivo:** `app/main.py:202-223`

**Detalhes:**
```python
allow_origin_regex = r"^https?://((192\.168\.\d+\.\d+|...)|([\w-]+\.loca\.lt|[\w-]+\.trycloudflare\.com))$"
```

**Questão:** Este regex está ativo em produção?

**Como Verificar:**
```bash
# Ver variável ENVIRONMENT em produção
flyctl config show --app app-financeiro | grep ENVIRONMENT
```

**Se ENVIRONMENT=production:** ✅ Safe (usa allowed_origins específicos)
**Se ENVIRONMENT=development em prod:** ⚠️ Problema

**Impacto da Correção:**
- Nenhum (já está correto se usar environment certo)

**Recomendação:** Verificar ENVIRONMENT em produção

---

### 7-13. Outras Médias

**Sem Criptografia de Dados em Repouso**
- **Impacto:** Se banco comprometido, dados legíveis
- **Correção:** Criptografia de campo (muito complexo)
- **Recomendação:** Só se regulamentação exigir (PCI-DSS, LGPD)

**Sem Limites de Valor em Transações**
- **Impacto:** Transações de bilhões de reais podem ser criadas
- **Correção:** Validação `amount <= 1000000`
- **Risco:** Pode bloquear transações legítimas grandes
- **Recomendação:** Adicionar se houver abuso

**API Keys com SHA-256**
- **Impacto Real:** Baixo (requer acesso ao banco para atacar)
- **Correção:** Migrar para bcrypt (complexo)
- **Recomendação:** Adiar

---

## 🟢 BAIXA SEVERIDADE (Boas Práticas)

### 14. Debug Mode

**Verificar:**
```bash
flyctl config show --app app-financeiro | grep DEBUG
```

**Se DEBUG=true em prod:** Mudar para false
**Se DEBUG=false:** ✅ OK

### 15. Headers de Segurança (CSP)

**Status:** Parcialmente implementado
**Faltando:** Content-Security-Policy
**Impacto:** Proteção adicional contra XSS
**Recomendação:** Implementar em fase 2

### 16-18. Logging, Validação de Upload, Request Size Limits

**Impacto:** Melhorias operacionais e de monitoramento
**Recomendação:** Roadmap futuro

---

## ✅ PONTOS FORTES DE SEGURANÇA

O projeto já implementa várias boas práticas:

1. ✅ **Bcrypt para Senhas** - Hashing forte com salt automático
2. ✅ **Política de Senha Forte** - 8+ chars, uppercase, lowercase, número, especial
3. ✅ **SQLAlchemy ORM** - Previne SQL injection com queries parametrizadas
4. ✅ **Rate Limiting** - Proteção contra brute-force em login
5. ✅ **Headers de Segurança** - X-Frame-Options, HSTS, X-Content-Type-Options
6. ✅ **Proteção contra Path Traversal** - Validação de paths em static files
7. ✅ **Sistema de Permissões** - RBAC bem implementado para household/family
8. ✅ **Validação de Tokens JWT** - Distingue access vs refresh tokens
9. ✅ **API Keys Hashed** - Nunca armazenados em plaintext
10. ✅ **Secrets no .gitignore** - Credenciais não versionadas

---

## 🎯 Plano de Ação Recomendado

### Fase 1: Correções Rápidas (Esta Semana)

**1.1 Atualizar Dependências Frontend**
```bash
cd frontend
npm audit
npm audit fix
npm test  # Verificar se nada quebrou
npm run build  # Testar build
```
**Esforço:** 2-4 horas
**Risco:** Médio (testar navegação)
**Benefício:** Remove 3 vulnerabilidades conhecidas

**1.2 Verificar e Fortalecer Secrets em Produção**
```bash
# Ver secrets atuais
flyctl secrets list --app app-financeiro

# Se SECRET_KEY for fraco, gerar novo:
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# Aplicar (usuários serão deslogados)
flyctl secrets set SECRET_KEY="<secret_gerado>" --app app-financeiro
```
**Esforço:** 30 minutos
**Risco:** Baixo (só desloga usuários)
**Benefício:** Previne forjamento de tokens

**1.3 Verificar Configurações de Ambiente**
```bash
# Verificar se DEBUG=false em produção
flyctl config show --app app-financeiro | grep DEBUG

# Verificar se ENVIRONMENT=production
flyctl config show --app app-financeiro | grep ENVIRONMENT
```
**Esforço:** 5 minutos
**Risco:** Zero
**Benefício:** Confirma configuração correta

---

### Fase 2: Melhorias de Segurança (Este Mês)

**2.1 Implementar Content-Security-Policy**
```python
# app/main.py - no middleware de headers
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https://app-financeiro.fly.dev"
)
```
**Esforço:** 2-3 horas
**Risco:** Médio (pode quebrar recursos externos)
**Benefício:** Proteção adicional contra XSS

**Testar em modo report-only primeiro:**
```python
"Content-Security-Policy-Report-Only": "..."  # Só avisa, não bloqueia
```

**2.2 Account Lockout após Tentativas Falhas**
```python
# Nova tabela
class LoginAttempt(Base):
    email: str
    failed_attempts: int = 0
    locked_until: datetime | None

# No endpoint de login:
if login_attempts.failed_attempts >= 5:
    if login_attempts.locked_until > datetime.now():
        raise HTTPException(423, "Conta bloqueada. Tente novamente em X minutos")
```
**Esforço:** 4-6 horas
**Risco:** Médio (usuários podem se trancar)
**Benefício:** Proteção adicional contra brute-force

**Precisa também:**
- Endpoint de unlock (via email ou admin)
- Email de notificação quando conta bloqueada

**2.3 Adicionar Logging de Segurança**
```python
# Criar logger específico
security_logger = logging.getLogger("security")

# Logar eventos importantes
security_logger.warning(
    "failed_login_attempt",
    extra={
        "email": email,
        "ip": request.client.host,
        "user_agent": request.headers.get("user-agent")
    }
)
```
**Esforço:** 3-4 horas
**Risco:** Baixo
**Benefício:** Detecção de ataques e auditoria

---

### Fase 3: Arquitetura (Se Necessário)

**3.1 Migrar para Redis (Só Se Múltiplas Máquinas)**

**Verificar necessidade:**
```bash
flyctl status --app app-financeiro
# Se Machines > 1: precisa Redis
# Se Machines = 1: memory:// funciona bem
```

**Se necessário:**
```bash
# Provisionar Redis
flyctl redis create

# Adicionar dependência
pip install redis

# Configurar
storage_uri = os.getenv("REDIS_URL", "memory://")
```
**Custo:** $5-10/mês + 2h dev
**Recomendação:** Só se escalar

**3.2 Migrar JWT para httpOnly Cookies (NÃO RECOMENDADO)**

**Por que NÃO fazer:**
- ❌ Muito invasivo (12-16 horas dev)
- ❌ QUEBRA: authStore, api client, token refresh
- ❌ Complexidade adicional (CORS credentials)
- ✅ Alternativa: CSP + sanitização (muito mais simples)

**Só fazer se:**
- Regulamentação exigir
- Múltiplos XSS descobertos
- App processar pagamentos (PCI-DSS)

---

## 📋 Checklist de Verificação

### Verificações Imediatas (5 minutos)

```bash
# 1. Ver secrets em produção
flyctl secrets list --app app-financeiro

# 2. Ver configuração de ambiente
flyctl config show --app app-financeiro

# 3. Ver quantas máquinas
flyctl status --app app-financeiro

# 4. Verificar vulnerabilidades npm
cd frontend && npm audit

# 5. Verificar se .env está protegido
git ls-files | grep "\.env$"  # Deve retornar vazio ou .env.example
```

### Correções Seguras (Baixo Risco)

- [ ] Rodar `npm audit fix`
- [ ] Gerar SECRET_KEY forte se necessário
- [ ] Confirmar DEBUG=false em produção
- [ ] Confirmar ENVIRONMENT=production

### Melhorias Médio Prazo

- [ ] Adicionar CSP header (modo report-only)
- [ ] Implementar account lockout
- [ ] Adicionar logging de segurança
- [ ] Adicionar limites de valor em transações

### NÃO Fazer (Muito Invasivo)

- ❌ Migrar JWT para cookies (a menos que necessário)
- ❌ Criptografia de campo (a menos que regulamentação)
- ❌ Redis (a menos que múltiplas máquinas)

---

## 🔧 Scripts Prontos para Uso

### Gerar Secret Forte
```bash
# JWT Secret (64 chars)
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"

# Database Password (32 chars)
python3 -c "import secrets; print('DB_PASS=' + secrets.token_urlsafe(32))"

# API Key (48 chars)
python3 -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(48))"
```

### Aplicar Secrets no Fly.io
```bash
# Um por vez
flyctl secrets set SECRET_KEY="xxx" --app app-financeiro

# Ou em lote
flyctl secrets set \
  SECRET_KEY="xxx" \
  OTHER_SECRET="yyy" \
  --app app-financeiro
```

### Verificar Segurança das Dependências
```bash
# Frontend
cd frontend
npm audit
npm audit fix --dry-run  # Ver o que vai mudar
npm audit fix             # Aplicar correções

# Backend
cd backend
pip install pip-audit
pip-audit
```

---

## 📊 Resumo por Esforço vs Impacto

### Alta Prioridade (Fazer Agora)
| Item | Esforço | Risco | Benefício | Status |
|------|---------|-------|-----------|--------|
| Verificar secrets prod | 5 min | Zero | Alto | ⚠️ A fazer |
| npm audit fix | 2-4h | Médio | Alto | ⚠️ A fazer |
| Secret forte (se necessário) | 30 min | Baixo | Alto | ⚠️ Verificar |

### Média Prioridade (Este Mês)
| Item | Esforço | Risco | Benefício | Status |
|------|---------|-------|-----------|--------|
| CSP header | 2-3h | Médio | Médio | 📅 Planejado |
| Account lockout | 4-6h | Médio | Médio | 📅 Planejado |
| Security logging | 3-4h | Baixo | Alto | 📅 Planejado |

### Baixa Prioridade (Só Se Necessário)
| Item | Esforço | Risco | Benefício | Status |
|------|---------|-------|-----------|--------|
| JWT → cookies | 12-16h | Alto | Médio | ❌ Não fazer |
| Redis rate limit | 2h + $5/mês | Médio | Baixo* | ⏸️ Se escalar |
| Encryption at rest | 20+ horas | Alto | Baixo** | ⏸️ Se regulado |

\* Benefício só existe se múltiplas máquinas
\** Benefício só existe se regulamentação exigir

---

## 🎯 Próximos Passos Sugeridos

1. **AGORA:** Rodar os comandos de verificação acima
2. **HOJE:** Me informar os resultados para avaliar riscos reais
3. **ESTA SEMANA:** Aplicar correções de alta prioridade que confirmarmos
4. **ESTE MÊS:** Planejar melhorias de média prioridade

---

## 📞 Como Proceder

Para cada correção, me informe:
1. ✅ **"Pode fazer"** - Implemento e testo
2. ⏸️ **"Depois"** - Adiciono ao backlog
3. ❌ **"Não fazer"** - Descarto da análise

**Exemplo:**
```
1. npm audit fix: ✅ Pode fazer
2. Secret forte: ⏸️ Verificar primeiro
3. JWT cookies: ❌ Não fazer
```

---

**Documento gerado em:** 2026-02-07
**Próxima revisão:** 2026-05-07 (trimestral)
**Contato para dúvidas:** Este documento deve ser revisado antes de implementar qualquer correção.
