# Esquema do Banco de Dados

## Diagrama ER

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'nodeTextColor': '#e2e8f0', 'attributeBackgroundColorOdd': '#1e293b', 'attributeBackgroundColorEven': '#0f172a'}}}%%
erDiagram
    %% CORE: Usuarios e Licencas
    USERS {
        int id PK
        int license_id FK
        string email UK
        string hashed_password
        string name
        bool is_active
        bool is_verified
        bool is_admin
        datetime created_at
    }

    LICENSES {
        int id PK
        int owner_user_id FK
        string key UK
        string code UK
        string type
        string status
        int max_users
        datetime start_date
        datetime end_date
    }

    HOUSEHOLD_MEMBERS {
        int id PK
        int license_id FK
        int user_id FK
        int invited_by_id FK
        string role
        bool can_create_transactions
        bool can_edit_shared
    }

    %% FINANCEIRO: Contas e Cartoes
    ACCOUNTS {
        int id PK
        int user_id FK
        string name
        string type
        decimal balance
        string currency
        string ownership_type
        bool is_active
    }

    CREDIT_CARDS {
        int id PK
        int account_id FK
        int user_id FK
        decimal credit_limit
        int closing_day
        int due_day
        string card_brand
        string last_four_digits
        bool is_active
    }

    CREDIT_CARD_INVOICES {
        int id PK
        int user_id FK
        int credit_card_id FK
        int document_id FK
        int payment_account_id FK
        int payment_transaction_id FK
        int reference_month
        int reference_year
        date closing_date
        date due_date
        decimal total_amount
        decimal paid_amount
        string status
    }

    %% TRANSACOES
    TRANSACTIONS {
        int id PK
        int user_id FK
        int account_id FK
        int category_id FK
        int merchant_id FK
        int document_id FK
        int credit_card_id FK
        int invoice_id FK
        int income_source_id FK
        int installment_series_id FK
        int recurring_id FK
        int linked_transaction_id FK
        string type
        decimal amount
        date date
        string description
        int installment_number
        int installment_total
        bool is_paid
        bool is_fixed
    }

    INSTALLMENT_SERIES {
        int id PK
        int user_id FK
        int account_id FK
        int category_id FK
        int merchant_id FK
        int credit_card_id FK
        string description
        string merchant_name
        decimal total_amount
        decimal installment_amount
        int installment_count
        date first_installment_date
        string status
        int paid_count
    }

    %% CATEGORIAS E MERCHANTS
    CATEGORIES {
        int id PK
        int parent_id FK
        int user_id FK
        string name
        string type
        string icon
        bool is_system
    }

    MERCHANTS {
        int id PK
        string name
        string normalized_name UK
        string cnpj
    }

    %% DOCUMENTOS
    DOCUMENTS {
        int id PK
        int user_id FK
        string file_path
        string file_hash
        string original_filename
        string status
        string document_type
        datetime processed_at
    }

    DOCUMENT_EXTRACTIONS {
        int id PK
        int document_id FK
        int version
        decimal amount
        date date
        string merchant_name
        json items
    }

    %% FONTES DE RENDA
    INCOME_SOURCES {
        int id PK
        int user_id FK
        int account_id FK
        int category_id FK
        string name
        string type
        decimal expected_amount
        string frequency
        int payment_day
        bool is_active
    }

    %% ORCAMENTOS
    BUDGETS {
        int id PK
        int user_id FK
        int year
        int month
        decimal total_income_planned
        decimal total_expense_planned
    }

    BUDGET_ITEMS {
        int id PK
        int budget_id FK
        int category_id FK
        decimal planned_amount
        bool is_fixed
        int priority
    }

    %% METAS
    GOALS {
        int id PK
        int user_id FK
        int account_id FK
        string name
        string type
        decimal target_amount
        decimal current_amount
        date target_date
        string status
    }

    GOAL_CONTRIBUTIONS {
        int id PK
        int goal_id FK
        int transaction_id FK
        decimal amount
        date contribution_date
    }

    %% DIVIDAS
    DEBTS {
        int id PK
        int user_id FK
        int account_id FK
        int installment_series_id FK
        string name
        string type
        string creditor
        decimal original_amount
        decimal current_balance
        decimal interest_rate
        string status
    }

    DEBT_PAYMENTS {
        int id PK
        int debt_id FK
        int transaction_id FK
        decimal amount
        decimal principal_amount
        decimal interest_amount
        date payment_date
    }

    %% RECORRENCIAS
    RECURRING_TRANSACTIONS {
        int id PK
        int user_id FK
        int account_id FK
        int category_id FK
        string name
        decimal amount
        string type
        string frequency
        int day_of_month
        string status
    }

    %% SERVICOS CONHECIDOS
    KNOWN_RECURRING_SERVICES {
        int id PK
        string name
        json patterns
        string default_category
        string default_frequency
        string logo_url
        bool is_active
        datetime created_at
    }

    %% RELACIONAMENTOS
    LICENSES ||--o{ USERS : "possui"
    LICENSES ||--o{ HOUSEHOLD_MEMBERS : "agrupa"
    USERS ||--o{ HOUSEHOLD_MEMBERS : "participa"
    USERS ||--o{ ACCOUNTS : "possui"
    ACCOUNTS ||--o| CREDIT_CARDS : "detalha"
    USERS ||--o{ CREDIT_CARDS : "possui"
    CREDIT_CARDS ||--o{ CREDIT_CARD_INVOICES : "gera"
    USERS ||--o{ TRANSACTIONS : "realiza"
    ACCOUNTS ||--o{ TRANSACTIONS : "movimenta"
    CATEGORIES ||--o{ TRANSACTIONS : "classifica"
    MERCHANTS ||--o{ TRANSACTIONS : "identifica"
    DOCUMENTS ||--o{ TRANSACTIONS : "comprova"
    CREDIT_CARDS ||--o{ TRANSACTIONS : "debita"
    CREDIT_CARD_INVOICES ||--o{ TRANSACTIONS : "agrupa"
    INCOME_SOURCES ||--o{ TRANSACTIONS : "origina"
    INSTALLMENT_SERIES ||--o{ TRANSACTIONS : "parcela"
    RECURRING_TRANSACTIONS ||--o{ TRANSACTIONS : "gera"
    USERS ||--o{ INSTALLMENT_SERIES : "possui"
    ACCOUNTS ||--o{ INSTALLMENT_SERIES : "vincula"
    CREDIT_CARDS ||--o{ INSTALLMENT_SERIES : "financia"
    USERS ||--o{ DOCUMENTS : "envia"
    DOCUMENTS ||--o{ DOCUMENT_EXTRACTIONS : "extrai"
    DOCUMENTS ||--o| CREDIT_CARD_INVOICES : "comprova"
    CATEGORIES ||--o{ CATEGORIES : "subcategoria"
    USERS ||--o{ CATEGORIES : "personaliza"
    USERS ||--o{ INCOME_SOURCES : "cadastra"
    ACCOUNTS ||--o{ INCOME_SOURCES : "recebe"
    CATEGORIES ||--o{ INCOME_SOURCES : "classifica"
    USERS ||--o{ BUDGETS : "planeja"
    BUDGETS ||--o{ BUDGET_ITEMS : "detalha"
    CATEGORIES ||--o{ BUDGET_ITEMS : "categoriza"
    USERS ||--o{ GOALS : "define"
    ACCOUNTS ||--o{ GOALS : "vincula"
    GOALS ||--o{ GOAL_CONTRIBUTIONS : "recebe"
    USERS ||--o{ DEBTS : "possui"
    DEBTS ||--o{ DEBT_PAYMENTS : "paga"
    INSTALLMENT_SERIES ||--o{ DEBTS : "origina"
    USERS ||--o{ RECURRING_TRANSACTIONS : "configura"
    ACCOUNTS ||--o{ RECURRING_TRANSACTIONS : "movimenta"
    CATEGORIES ||--o{ RECURRING_TRANSACTIONS : "classifica"
```

---

## Fluxo Principal: Cartao de Credito

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'nodeTextColor': '#e2e8f0'}}}%%
flowchart TB
    subgraph Account["ACCOUNTS"]
        A["type='credit_card'"]
    end

    subgraph Card["CREDIT_CARDS"]
        CC["credit_limit<br/>closing_day<br/>due_day"]
    end

    subgraph Invoice["CREDIT_CARD_INVOICES"]
        INV["reference_month/year<br/>closing_date<br/>due_date<br/>total_amount<br/>status"]
    end

    subgraph Transactions["TRANSACTIONS"]
        TX["credit_card_id<br/>invoice_id<br/>amount<br/>date"]
    end

    Account -->|"1:1"| Card
    Card -->|"1:N"| Invoice
    Invoice -->|"1:N"| Transactions

    Note["O total_amount da fatura<br/>e calculado das transacoes"]
```

---

## Fluxo de Parcelas (Installments)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'nodeTextColor': '#e2e8f0'}}}%%
flowchart TB
    subgraph Series["INSTALLMENT_SERIES"]
        IS["description: 'Loja X'<br/>total_amount: 1200.00<br/>installment_amount: 100.00<br/>installment_count: 12<br/>credit_card_id: 5<br/>status: 'active'"]
    end

    subgraph Transactions["TRANSACTIONS (12 parcelas)"]
        TX1["1/12 - Jan - R$100"]
        TX2["2/12 - Fev - R$100"]
        TX3["3/12 - Mar - R$100"]
        TXN["...<br/>12/12 - Dez - R$100"]
    end

    Series -->|"1:N"| TX1
    Series -->|"1:N"| TX2
    Series -->|"1:N"| TX3
    Series -->|"1:N"| TXN
```

**Exemplo: Compra parcelada R$ 1.200 em 12x de R$ 100**

| Parcela | Data | Valor | Fatura |
|---------|------|-------|--------|
| 1/12 | 2025-01-15 | R$ 100 | Jan/2025 |
| 2/12 | 2025-02-15 | R$ 100 | Fev/2025 |
| 3/12 | 2025-03-15 | R$ 100 | Mar/2025 |
| ... | ... | ... | ... |
| 12/12 | 2025-12-15 | R$ 100 | Dez/2025 |

---

## Calculo de Saldos

### Conta Bancaria (bank/wallet)

```
Saldo = account.balance + SUM(transactions)

Onde:
  - income = +amount
  - expense = -amount
```

### Cartao de Credito

```
Limite Usado = SUM(transactions WHERE credit_card_id = X)
Limite Disponivel = credit_card.credit_limit - Limite Usado
Total da Fatura = SUM(transactions WHERE invoice_id = Y)
```

### Transferencia entre Contas

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'nodeTextColor': '#e2e8f0'}}}%%
flowchart LR
    subgraph ContaA["Conta A"]
        TxOut["tx_out<br/>id: 1<br/>linked_id: 2<br/>SAIDA (-)"]
    end

    subgraph ContaB["Conta B"]
        TxIn["tx_in<br/>id: 2<br/>linked_id: 1<br/>ENTRADA (+)"]
    end

    TxOut <-->|"linked_transaction_id"| TxIn
```

**Logica:**
- Se `id < linked_transaction_id` = SAIDA (subtrair)
- Se `id > linked_transaction_id` = ENTRADA (somar)

**Contas permitidas:** `wallet`, `bank`, `investment`
**NAO permitido:** `credit_card`

---

## Relacionamentos Principais

### Hierarquia de Usuarios

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'nodeTextColor': '#e2e8f0'}}}%%
flowchart TB
    L["LICENSE (Plano)"]
    U["USERS (Usuarios do plano)"]
    H["HOUSEHOLD_MEMBERS (Membros da familia)"]

    L --> U
    U --> H
```

### Hierarquia Financeira

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1E3A5F', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#4ade80', 'lineColor': '#4ade80', 'secondaryColor': '#0f172a', 'tertiaryColor': '#1e293b', 'background': 'transparent', 'mainBkg': '#1e293b', 'textColor': '#e2e8f0', 'nodeTextColor': '#e2e8f0'}}}%%
flowchart TB
    User["USER"]

    subgraph Financial["Financeiro"]
        Accounts["ACCOUNTS"]
        Transactions["TRANSACTIONS"]
        CreditCards["CREDIT_CARDS"]
        Invoices["INVOICES"]
        Installments["INSTALLMENT_SERIES"]
    end

    subgraph Organization["Organizacao"]
        Categories["CATEGORIES"]
        Subcategories["Subcategorias"]
    end

    subgraph Planning["Planejamento"]
        Budgets["BUDGETS"]
        BudgetItems["BUDGET_ITEMS"]
        Goals["GOALS"]
        Contributions["CONTRIBUTIONS"]
        Debts["DEBTS"]
        Payments["PAYMENTS"]
    end

    subgraph Automation["Automacao"]
        Recurring["RECURRING"]
        IncomeSources["INCOME_SOURCES"]
        Documents["DOCUMENTS"]
    end

    User --> Accounts
    Accounts --> Transactions
    Accounts --> CreditCards
    CreditCards --> Invoices
    Invoices --> Transactions
    Accounts --> Installments
    Installments --> Transactions

    User --> Categories
    Categories --> Subcategories

    User --> Budgets
    Budgets --> BudgetItems
    User --> Goals
    Goals --> Contributions
    User --> Debts
    Debts --> Payments

    User --> Recurring
    Recurring --> Transactions
    User --> IncomeSources
    IncomeSources --> Transactions
    User --> Documents
```

---

## Tipos e Status

### Account.type
| Valor | Descricao |
|-------|-----------|
| `wallet` | Carteira fisica |
| `bank` | Conta bancaria |
| `credit_card` | Cartao de credito |
| `investment` | Investimento |

### Transaction.type
| Valor | Descricao |
|-------|-----------|
| `income` | Receita |
| `expense` | Despesa |
| `transfer` | Transferencia entre contas |

### InvoiceStatus
| Valor | Descricao |
|-------|-----------|
| `open` | Aberta (acumulando) |
| `closed` | Fechada (aguardando pagamento) |
| `paid` | Paga |
| `partial` | Parcialmente paga |
| `overdue` | Vencida |

### InstallmentSeriesStatus
| Valor | Descricao |
|-------|-----------|
| `active` | Em andamento |
| `completed` | Todas pagas |
| `cancelled` | Cancelada |

### ownership_type
| Valor | Descricao |
|-------|-----------|
| `personal` | Pessoal |
| `household` | Compartilhada (familia) |

### RecurringTransaction.frequency
| Valor | Descricao |
|-------|-----------|
| `daily` | Diaria |
| `weekly` | Semanal |
| `monthly` | Mensal |
| `yearly` | Anual |

### RecurringTransaction.status
| Valor | Descricao |
|-------|-----------|
| `active` | Ativa |
| `paused` | Pausada |
| `cancelled` | Cancelada |
