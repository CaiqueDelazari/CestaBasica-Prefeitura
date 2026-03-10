import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path


def normalize_email(raw_email, matricula):
    if raw_email is None:
        return f"sem-email-{matricula}@prefeitura.local"
    value = str(raw_email).strip().lower()
    if not value or value == "null":
        return f"sem-email-{matricula}@prefeitura.local"
    return value


def get_or_create_id(db, table, name):
    row = db.execute(f"SELECT id FROM {table} WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cursor = db.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
    return cursor.lastrowid


def get_or_create_department(db, department_name, secretariat_id):
    row = db.execute(
        """
        SELECT id
        FROM hr_departments
        WHERE name = ? AND secretariat_id = ?
        """,
        (department_name, secretariat_id),
    ).fetchone()
    if row:
        return row["id"]
    cursor = db.execute(
        "INSERT INTO hr_departments (name, secretariat_id) VALUES (?, ?)",
        (department_name, secretariat_id),
    )
    return cursor.lastrowid


def get_or_create_card(db, card_code, now_iso):
    row = db.execute(
        "SELECT id FROM hr_access_cards WHERE card_code = ?",
        (card_code,),
    ).fetchone()
    if row:
        return row["id"]
    cursor = db.execute(
        """
        INSERT INTO hr_access_cards (card_code, status, issued_at, updated_at)
        VALUES (?, 'active', ?, ?)
        """,
        (card_code, now_iso, now_iso),
    )
    return cursor.lastrowid


def import_data(db_path, input_path):
    with input_path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    now_iso = datetime.now().isoformat(timespec="seconds")

    inserted = 0
    skipped = 0

    try:
        for item in records:
            matricula = str(item.get("matricula", "")).strip()
            nome = str(item.get("nome", "")).strip()
            vinculo = str(item.get("vinculo", "")).strip() or "NAO INFORMADO"
            lotacao = str(item.get("lotacao", "")).strip() or "NAO INFORMADA"
            secretaria = str(item.get("secretaria", "")).strip() or "NAO INFORMADA"
            cargo = str(item.get("cargo", "")).strip() or "NAO INFORMADO"
            cartao = str(item.get("cartao", "")).strip()

            if not matricula or not nome:
                skipped += 1
                continue

            employee_exists = db.execute(
                "SELECT id FROM hr_employees WHERE registration_number = ?",
                (matricula,),
            ).fetchone()
            if employee_exists:
                skipped += 1
                continue

            email = normalize_email(item.get("email"), matricula)
            email_exists = db.execute(
                "SELECT id FROM hr_employees WHERE email = ?",
                (email,),
            ).fetchone()
            if email_exists:
                email = f"sem-email-{matricula}@prefeitura.local"

            secretariat_id = get_or_create_id(db, "hr_secretariats", secretaria)
            bond_id = get_or_create_id(db, "hr_employment_bonds", vinculo)
            position_id = get_or_create_id(db, "hr_job_positions", cargo)
            department_id = get_or_create_department(db, lotacao, secretariat_id)

            card_code = cartao if cartao else f"SEM-CARTAO-{matricula}"
            card_id = get_or_create_card(db, card_code, now_iso)

            card_in_use = db.execute(
                "SELECT id FROM hr_employees WHERE access_card_id = ?",
                (card_id,),
            ).fetchone()
            if card_in_use:
                card_id = get_or_create_card(
                    db,
                    f"{card_code}-ALT-{matricula}",
                    now_iso,
                )

            db.execute(
                """
                INSERT INTO hr_employees (
                    registration_number,
                    full_name,
                    employment_bond_id,
                    department_id,
                    secretariat_id,
                    job_position_id,
                    email,
                    access_card_id,
                    registration_source,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?, ?)
                """,
                (
                    matricula,
                    nome,
                    bond_id,
                    department_id,
                    secretariat_id,
                    position_id,
                    email,
                    card_id,
                    now_iso,
                    now_iso,
                ),
            )
            inserted += 1

        db.commit()
    finally:
        db.close()

    return inserted, skipped, len(records)


def main():
    parser = argparse.ArgumentParser(description="Importa funcionarios para o SQLite.")
    parser.add_argument("--input", required=True, help="Caminho do JSON tratado.")
    parser.add_argument("--db", required=True, help="Caminho do banco SQLite.")
    args = parser.parse_args()

    input_path = Path(args.input)
    db_path = Path(args.db)
    inserted, skipped, total = import_data(db_path, input_path)
    print(f"Total lidos: {total}")
    print(f"Inseridos: {inserted}")
    print(f"Ignorados: {skipped}")


if __name__ == "__main__":
    main()
