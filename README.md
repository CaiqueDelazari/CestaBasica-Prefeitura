# Sistema de Cesta Basica - Prefeitura

Sistema web simples para controle de entrega de cesta basica com:

- Login
- Cadastro de servidores e tag RFID
- Registro do dia de chegada da cesta
- Leitura de cracha RFID pelo leitor USB (como teclado)
- Bloqueio de segunda retirada no mesmo mes
- Limpeza automatica dos registros apos 27 dias da ultima data de chegada

## Requisitos

- Python 3.10+ (testado com Python 3.14)

## Como rodar

1. Abra o terminal na pasta do projeto.
2. Crie e ative ambiente virtual:

   - PowerShell:
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```

3. Instale dependencias:
   ```powershell
   pip install -r requirements.txt
   ```

4. Execute:
   ```powershell
   python app.py
   ```

5. Acesse no navegador:
   - http://127.0.0.1:5000

## Login inicial

- Usuario: `admin`
- Senha: `admin123`

## Observacoes sobre RFID

- O leitor RFID USB normalmente funciona como teclado HID.
- Ao bater o cracha, ele preenche o campo de tag e voce registra a retirada.
- Cadastre antes cada servidor com sua respectiva tag RFID na tela **Servidores**.

## Regra de limpeza (27 dias)

- O sistema verifica automaticamente se passaram 27 dias da ultima data de chegada registrada.
- Se passou, ele limpa os registros de retirada e ciclo anterior, para iniciar novo ciclo.
