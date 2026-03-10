# Arquitetura - Gestao de Funcionarios

## 1) Modelagem normalizada

Entidades principais:

- `hr_employees` (funcionario)
- `hr_employment_bonds` (vinculo)
- `hr_departments` (lotacao)
- `hr_secretariats` (secretaria)
- `hr_job_positions` (cargo)
- `hr_access_cards` (cartao de acesso)

Relacionamentos:

- Funcionario N:1 Vinculo
- Funcionario N:1 Lotacao
- Funcionario N:1 Secretaria
- Funcionario N:1 Cargo
- Funcionario 1:1 Cartao

## 2) Regras de negocio implementadas

- Se lotacao for `Domicilio`, a matricula e obrigatoria e manual.
- Demais lotacoes:
  - se matricula vier preenchida, usa manual;
  - se vier vazia, gera automaticamente no padrao `AUTO-ANO-XXXX`.
- Filtros por nome, matricula, secretaria e vinculo.
- Abas por categoria:
  - Todos
  - Domicilio
  - Demais setores

## 3) Estrutura backend (atual e sugerida)

Atual:

- `app.py` centraliza rotas, regras e persistencia.

Evolucao sugerida:

```text
app/
  routes/
    funcionarios_routes.py
  services/
    funcionario_service.py
    matricula_service.py
  repositories/
    funcionario_repository.py
    lookup_repository.py
  db/
    connection.py
    schema_funcionarios.sql
```

## 4) Interface implementada

Tela `Funcionarios` com:

- Formulario de cadastro completo:
  - Matricula
  - Nome
  - Vinculo
  - Lotacao
  - Secretaria
  - Cargo
  - Email
  - Cartao de acesso
- Abas de categorias
- Filtros de consulta
- Tabela de listagem com todos os campos principais
