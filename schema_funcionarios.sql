PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS hr_employment_bonds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hr_secretariats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hr_departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    secretariat_id INTEGER NOT NULL,
    UNIQUE(name, secretariat_id),
    FOREIGN KEY(secretariat_id) REFERENCES hr_secretariats(id)
);

CREATE TABLE IF NOT EXISTS hr_job_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS hr_access_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    issued_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hr_employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_number TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    employment_bond_id INTEGER NOT NULL,
    department_id INTEGER NOT NULL,
    secretariat_id INTEGER NOT NULL,
    job_position_id INTEGER NOT NULL,
    email TEXT NOT NULL UNIQUE,
    access_card_id INTEGER NOT NULL UNIQUE,
    registration_source TEXT NOT NULL CHECK (registration_source IN ('manual', 'auto')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(employment_bond_id) REFERENCES hr_employment_bonds(id),
    FOREIGN KEY(department_id) REFERENCES hr_departments(id),
    FOREIGN KEY(secretariat_id) REFERENCES hr_secretariats(id),
    FOREIGN KEY(job_position_id) REFERENCES hr_job_positions(id),
    FOREIGN KEY(access_card_id) REFERENCES hr_access_cards(id)
);

CREATE INDEX IF NOT EXISTS idx_hr_employees_name ON hr_employees(full_name);
CREATE INDEX IF NOT EXISTS idx_hr_employees_department ON hr_employees(department_id);
CREATE INDEX IF NOT EXISTS idx_hr_employees_secretariat ON hr_employees(secretariat_id);
CREATE INDEX IF NOT EXISTS idx_hr_employees_bond ON hr_employees(employment_bond_id);
