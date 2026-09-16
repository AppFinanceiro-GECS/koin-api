# Convencoes de Codigo

## Backend (Python)

### Nomenclatura

```python
# Classes: PascalCase
class TransactionService:
    pass

# Funcoes e variaveis: snake_case
def calculate_total(transactions: list) -> Decimal:
    total_amount = Decimal(0)
    return total_amount

# Constantes: UPPER_SNAKE_CASE
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# Arquivos: snake_case
# transaction_service.py
```

### Estrutura de Modulo

```python
# 1. Imports da biblioteca padrao
from datetime import datetime
from decimal import Decimal

# 2. Imports de terceiros
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 3. Imports locais
from app.core.deps import CurrentUser, DbSession
from app.models import Transaction
from .schemas import TransactionCreate, TransactionResponse

# 4. Constantes
ITEMS_PER_PAGE = 50

# 5. Classes/Funcoes
class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, user_id: int) -> list[Transaction]:
        ...
```

### Docstrings

```python
async def create_transaction(
    self,
    user: User,
    data: TransactionCreate,
) -> Transaction:
    """
    Cria uma nova transacao para o usuario.

    Args:
        user: Usuario autenticado
        data: Dados da transacao

    Returns:
        Transacao criada

    Raises:
        HTTPException: Se a conta nao existir
    """
```

---

## Frontend (TypeScript)

### Nomenclatura

```typescript
// Componentes: PascalCase
function TransactionList() { ... }

// Hooks: camelCase com prefixo use
function useTransactions() { ... }

// Stores: camelCase com sufixo Store
const useAuthStore = create(...)

// Tipos/Interfaces: PascalCase
interface Transaction { ... }
type TransactionType = 'income' | 'expense';

// Constantes: UPPER_SNAKE_CASE
const MAX_FILE_SIZE = 10 * 1024 * 1024;

// Arquivos:
// Componentes: PascalCase.tsx
// Outros: camelCase.ts
```

### Estrutura de Componente

```typescript
// 1. Imports
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { transactionsApi } from '@/services/api';

// 2. Types
interface TransactionListProps {
  accountId?: number;
  onSelect?: (tx: Transaction) => void;
}

// 3. Component
export function TransactionList({ accountId, onSelect }: TransactionListProps) {
  // 3.1 State
  const [filter, setFilter] = useState('');

  // 3.2 Queries
  const { data, isLoading } = useQuery({
    queryKey: ['transactions', accountId],
    queryFn: () => transactionsApi.list({ account_id: accountId }),
  });

  // 3.3 Effects
  useEffect(() => {
    // ...
  }, []);

  // 3.4 Handlers
  const handleClick = (tx: Transaction) => {
    onSelect?.(tx);
  };

  // 3.5 Render
  if (isLoading) return <Loading />;

  return (
    <div>
      {data?.map(tx => (
        <TransactionItem key={tx.id} transaction={tx} onClick={handleClick} />
      ))}
    </div>
  );
}
```

---

## Git Workflow

### Branches

```bash
# 1. Criar branch a partir de main
git checkout main
git pull origin main
git checkout -b feature/nova-funcionalidade

# 2. Desenvolver e commitar
git add .
git commit -m "feat: adiciona nova funcionalidade"

# 3. Manter atualizado com main
git fetch origin
git rebase origin/main

# 4. Push e criar PR
git push -u origin feature/nova-funcionalidade
```

### Convencao de Commits

Seguimos [Conventional Commits](https://conventionalcommits.org/):

```
<tipo>(<escopo>): <descricao>

[corpo opcional]

[rodape opcional]
```

**Tipos:**
| Tipo | Descricao |
|------|-----------|
| `feat` | Nova funcionalidade |
| `fix` | Correcao de bug |
| `docs` | Documentacao |
| `style` | Formatacao |
| `refactor` | Refatoracao |
| `test` | Testes |
| `chore` | Manutencao |

**Exemplos:**
```
feat(transactions): adiciona filtro por categoria
fix(auth): corrige refresh de token expirado
docs(readme): atualiza instrucoes de instalacao
refactor(documents): extrai validacao para service separado
```

### Code Review

Antes de aprovar um PR, verificar:

1. **Funcionalidade**: Codigo faz o que deveria?
2. **Testes**: Tem cobertura adequada?
3. **Seguranca**: Nao introduz vulnerabilidades?
4. **Performance**: Nao causa regressao?
5. **Documentacao**: Esta atualizada?

---

## Padroes de UI/UX

### Design Tokens

**Cores (Tailwind)**
```javascript
primary: {
  900: '#1E3A5F',  // Brand navy (main)
  400: '#829ab1',
}
accent: {
  400: '#4ade80',  // Brand green (main)
}
biveto: {
  navy: '#1E3A5F',
  green: '#4ade80',
}
expense: '#ef4444',  // Red
income: '#22c55e',   // Green
```

**Tipografia**
```javascript
fontFamily: {
  sans: ['Inter', 'system-ui', 'sans-serif'],
}
```

**Dark Mode:** `darkMode: 'class'`

### Padroes de Componente

| Padrao | Uso | Classe CSS |
|--------|-----|------------|
| Cards | Containers | `.card` |
| Buttons | Acoes primarias | `.btn-primary` |
| Buttons | Acoes secundarias | `.btn-secondary` |
| Inputs | Campos de formulario | `.input` |
| Avatar | Imagens de perfil | `.avatar` |
| Gradiente | Backgrounds especiais | `.gradient-biveto` |

### Estados de Loading/Empty/Error

| Componente | Loading | Empty | Error |
|------------|---------|-------|-------|
| Dashboard | Spinner | N/A | Toast |
| Lists | Skeleton | EmptyState | Toast |
| Upload | Progress bar | UploadSelector | Inline message |
| Forms | Button disabled | N/A | Inline message |

---

## Seguranca

### Backend

- **Nunca** expor senhas ou API keys em logs
- Usar `bcrypt` para hashing de senhas
- Validar **todos** os inputs com Pydantic
- Verificar ownership em todas as operacoes
- Rate limiting em endpoints sensiveis

### Frontend

- **Nunca** armazenar tokens em localStorage (usar Zustand memory)
- Sanitizar inputs do usuario
- Usar HTTPS em producao
- Nao expor dados sensiveis em console.log

---

## Performance

### Backend

- Usar queries async com SQLAlchemy
- Implementar paginacao em listagens
- Evitar N+1 queries (usar JOINs)
- Cachear dados estaticos

### Frontend

- Usar React Query para cache de servidor
- Implementar selectors no Zustand
- Lazy load de componentes pesados
- Otimizar re-renders com memo/useMemo
