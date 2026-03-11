import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import unicodedata

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "cesta_basica.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "trocar-essa-chave-em-producao"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_number TEXT UNIQUE,
            name TEXT NOT NULL,
            rfid_tag TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS basket_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arrival_date TEXT NOT NULL,
            available_date TEXT,
            basket_brand TEXT,
            supplier_name TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            basket_cycle_id INTEGER NOT NULL,
            claim_date TEXT NOT NULL,
            UNIQUE(employee_id, basket_cycle_id),
            FOREIGN KEY(employee_id) REFERENCES employees(id),
            FOREIGN KEY(basket_cycle_id) REFERENCES basket_cycles(id)
        );

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
        """
    )

    cycle_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(basket_cycles)").fetchall()
    }
    if "available_date" not in cycle_columns:
        db.execute("ALTER TABLE basket_cycles ADD COLUMN available_date TEXT")
    if "basket_brand" not in cycle_columns:
        db.execute("ALTER TABLE basket_cycles ADD COLUMN basket_brand TEXT")
    if "supplier_name" not in cycle_columns:
        db.execute("ALTER TABLE basket_cycles ADD COLUMN supplier_name TEXT")
        db.execute(
            """
            UPDATE basket_cycles
            SET supplier_name = basket_brand
            WHERE supplier_name IS NULL
              AND basket_brand IS NOT NULL
            """
        )

    employee_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(employees)").fetchall()
    }
    if "registration_number" not in employee_columns:
        db.execute("ALTER TABLE employees ADD COLUMN registration_number TEXT")
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_registration_number
        ON employees(registration_number)
        """
    )

    claim_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(claims)").fetchall()
    }
    if "claim_source" not in claim_columns:
        db.execute("ALTER TABLE claims ADD COLUMN claim_source TEXT NOT NULL DEFAULT 'legacy'")
    if "hr_employee_id" not in claim_columns:
        db.execute("ALTER TABLE claims ADD COLUMN hr_employee_id INTEGER")

    user_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(users)").fetchall()
    }
    if "role" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'adm'")
        db.execute("UPDATE users SET role = 'superadm' WHERE username = 'admin'")

    admin = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "superadm"),
        )
    else:
        db.execute("UPDATE users SET role = 'superadm' WHERE username = 'admin'")

    if not db.execute("SELECT id FROM employees LIMIT 1").fetchone():
        demo_employees = [
            ("1001", "Maria Silva", "RFID001"),
            ("1002", "Joao Santos", "RFID002"),
            ("1003", "Ana Souza", "RFID003"),
        ]
        db.executemany(
            "INSERT INTO employees (registration_number, name, rfid_tag) VALUES (?, ?, ?)",
            demo_employees,
        )

    if not db.execute("SELECT id FROM hr_employment_bonds LIMIT 1").fetchone():
        db.executemany(
            "INSERT INTO hr_employment_bonds (name) VALUES (?)",
            [
                ("Efetivo",),
                ("Comissionado",),
                ("Temporario",),
                ("Estagiario",),
            ],
        )

    if not db.execute("SELECT id FROM hr_secretariats LIMIT 1").fetchone():
        db.executemany(
            "INSERT INTO hr_secretariats (name) VALUES (?)",
            [
                ("Saude",),
                ("Educacao",),
                ("Assistencia Social",),
                ("Administracao",),
            ],
        )

    if not db.execute("SELECT id FROM hr_job_positions LIMIT 1").fetchone():
        db.executemany(
            "INSERT INTO hr_job_positions (name) VALUES (?)",
            [
                ("Assistente Administrativo",),
                ("Tecnico de Enfermagem",),
                ("Professor",),
                ("Analista",),
            ],
        )

    if not db.execute("SELECT id FROM hr_departments LIMIT 1").fetchone():
        secretariats = {
            row["name"]: row["id"]
            for row in db.execute("SELECT id, name FROM hr_secretariats").fetchall()
        }
        departments = [
            ("Domelia", secretariats["Assistencia Social"]),
            ("Posto Central", secretariats["Saude"]),
            ("Escola Municipal", secretariats["Educacao"]),
            ("Recursos Humanos", secretariats["Administracao"]),
        ]
        db.executemany(
            "INSERT INTO hr_departments (name, secretariat_id) VALUES (?, ?)",
            departments,
        )

    db.commit()


def current_cycle():
    db = get_db()
    return db.execute(
        """
        SELECT
            id,
            arrival_date,
            available_date,
            COALESCE(supplier_name, basket_brand) AS supplier_name
        FROM basket_cycles
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def clean_if_needed():
    db = get_db()
    cycle = current_cycle()
    if not cycle:
        return

    arrival = datetime.strptime(cycle["arrival_date"], "%Y-%m-%d").date()
    reset_limit = arrival + timedelta(days=27)
    if date.today() >= reset_limit:
        db.execute("DELETE FROM claims")
        db.execute("DELETE FROM basket_cycles")
        db.commit()


def require_login():
    if "user_id" not in session:
        return False
    return True


def redirect_to_index_tab(tab_name):
    return redirect(url_for("index", tab=tab_name))


def get_current_user():
    if "current_user" in g:
        return g.current_user
    user_id = session.get("user_id")
    if not user_id:
        g.current_user = None
        return None
    user = get_db().execute(
        "SELECT id, username, role FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    g.current_user = user
    return user


def is_superadm():
    user = get_current_user()
    return bool(user and user["role"] == "superadm")


def require_superadm_or_redirect(endpoint="index", **kwargs):
    if is_superadm():
        return None
    flash("Apenas superadm pode realizar essa acao.", "error")
    return redirect(url_for(endpoint, **kwargs))


def log_action(action, details=""):
    user = get_current_user()
    if user:
        user_id = user["id"]
        username = user["username"]
        role = user["role"]
    else:
        user_id = None
        username = "sistema"
        role = "system"

    get_db().execute(
        """
        INSERT INTO audit_logs (user_id, username, role, action, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            role,
            action,
            details,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    get_db().commit()


@app.context_processor
def inject_user_context():
    user = get_current_user()
    return {
        "current_user": user,
        "is_superadm_user": bool(user and user["role"] == "superadm"),
    }


@app.template_filter("mask_card")
def mask_card(card_value):
    raw = "" if card_value is None else str(card_value).strip()
    if not raw:
        return "********"
    if len(raw) <= 4:
        return "*" * len(raw)
    return "*" * (len(raw) - 4) + raw[-4:]


def normalize_tag_value(tag_value):
    raw = "" if tag_value is None else str(tag_value).strip()
    if not raw:
        return ""
    alnum = "".join(ch for ch in raw if ch.isalnum())
    if not alnum:
        return ""
    if alnum.isdigit():
        return alnum.lstrip("0") or "0"
    return alnum.upper()


def find_claimant_by_tag(db, raw_tag):
    # Fast path: exact match in HR cards
    hr_exact = db.execute(
        """
        SELECT he.id AS employee_id, he.full_name AS employee_name, ac.card_code AS card_value
        FROM hr_employees he
        JOIN hr_access_cards ac ON ac.id = he.access_card_id
        WHERE ac.card_code = ?
        LIMIT 1
        """,
        (raw_tag,),
    ).fetchone()
    if hr_exact:
        return {
            "source": "hr",
            "employee_id": hr_exact["employee_id"],
            "employee_name": hr_exact["employee_name"],
            "card_value": hr_exact["card_value"],
        }

    # Fast path: exact match in legacy tags
    legacy_exact = db.execute(
        "SELECT id, name, rfid_tag FROM employees WHERE rfid_tag = ? LIMIT 1",
        (raw_tag,),
    ).fetchone()
    if legacy_exact:
        return {
            "source": "legacy",
            "employee_id": legacy_exact["id"],
            "employee_name": legacy_exact["name"],
            "card_value": legacy_exact["rfid_tag"],
        }

    normalized_input = normalize_tag_value(raw_tag)
    if not normalized_input:
        return None

    # Fallback: normalized match (handles leading zeros and format differences)
    hr_rows = db.execute(
        """
        SELECT he.id AS employee_id, he.full_name AS employee_name, ac.card_code AS card_value
        FROM hr_employees he
        JOIN hr_access_cards ac ON ac.id = he.access_card_id
        """
    ).fetchall()
    for row in hr_rows:
        if normalize_tag_value(row["card_value"]) == normalized_input:
            return {
                "source": "hr",
                "employee_id": row["employee_id"],
                "employee_name": row["employee_name"],
                "card_value": row["card_value"],
            }

    legacy_rows = db.execute("SELECT id, name, rfid_tag FROM employees").fetchall()
    for row in legacy_rows:
        if normalize_tag_value(row["rfid_tag"]) == normalized_input:
            return {
                "source": "legacy",
                "employee_id": row["id"],
                "employee_name": row["name"],
                "card_value": row["rfid_tag"],
            }

    return None


def normalize_text(value):
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").casefold()


def is_domelia_department(department_name):
    normalized = normalize_text(department_name)
    return normalized in {"domelia", "domicilio"}


def generate_registration_number(db):
    year = datetime.now().year
    prefix = f"AUTO-{year}-"
    count = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM hr_employees
        WHERE registration_source = 'auto'
          AND registration_number LIKE ?
        """,
        (f"{prefix}%",),
    ).fetchone()["total"]

    while True:
        candidate = f"{prefix}{count + 1:04d}"
        exists = db.execute(
            "SELECT id FROM hr_employees WHERE registration_number = ?",
            (candidate,),
        ).fetchone()
        if not exists:
            return candidate
        count += 1


def fetch_hr_lookups(db):
    return {
        "bonds": db.execute(
            "SELECT id, name FROM hr_employment_bonds ORDER BY name"
        ).fetchall(),
        "secretariats": db.execute(
            "SELECT id, name FROM hr_secretariats ORDER BY name"
        ).fetchall(),
        "departments": db.execute(
            """
            SELECT d.id, d.name, d.secretariat_id, s.name AS secretariat_name
            FROM hr_departments d
            JOIN hr_secretariats s ON s.id = d.secretariat_id
            ORDER BY s.name, d.name
            """
        ).fetchall(),
        "positions": db.execute(
            "SELECT id, name FROM hr_job_positions ORDER BY name"
        ).fetchall(),
    }


@app.route("/", methods=["GET"])
def index():
    if not require_login():
        return redirect(url_for("login"))

    clean_if_needed()

    cycle = current_cycle()
    db = get_db()
    claims = db.execute(
        """
        SELECT
            c.claim_date,
            COALESCE(le.name, he.full_name) AS name,
            COALESCE(le.rfid_tag, ac.card_code) AS rfid_tag
        FROM claims c
        LEFT JOIN employees le ON le.id = c.employee_id
        LEFT JOIN hr_employees he ON he.id = c.hr_employee_id
        LEFT JOIN hr_access_cards ac ON ac.id = he.access_card_id
        ORDER BY c.id DESC
        LIMIT 20
        """
    ).fetchall()
    recent_logs = db.execute(
        """
        SELECT username, role, action, details, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT 10
        """
    ).fetchall()
    allowed_tabs = {"fornecedor", "chegada", "disponivel", "retirada"}
    active_tab = request.args.get("tab", "retirada")
    if active_tab not in allowed_tabs:
        active_tab = "retirada"
    return render_template(
        "index.html",
        cycle=cycle,
        claims=claims,
        recent_logs=recent_logs,
        active_tab=active_tab,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Usuario ou senha invalidos.", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        log_action("login", "Usuario autenticado no sistema")
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    if require_login():
        log_action("logout", "Usuario saiu do sistema")
    session.clear()
    return redirect(url_for("login"))


@app.route("/set-arrival", methods=["POST"])
def set_arrival():
    if not require_login():
        return redirect(url_for("login"))
    denied = require_superadm_or_redirect("index", tab="chegada")
    if denied:
        return denied

    clean_if_needed()
    arrival_date = request.form.get("arrival_date", "").strip()
    try:
        datetime.strptime(arrival_date, "%Y-%m-%d")
    except ValueError:
        flash("Data invalida. Use o formato correto.", "error")
        return redirect_to_index_tab("chegada")

    db = get_db()
    cycle = current_cycle()
    if cycle:
        db.execute(
            "UPDATE basket_cycles SET arrival_date = ? WHERE id = ?",
            (arrival_date, cycle["id"]),
        )
    else:
        db.execute(
            "INSERT INTO basket_cycles (arrival_date, created_at) VALUES (?, ?)",
            (arrival_date, datetime.now().isoformat(timespec="seconds")),
        )
    db.commit()
    log_action("update_cycle_arrival", f"Data de chegada definida para {arrival_date}")
    flash("Dia de chegada salvo para o ciclo mensal atual.", "success")
    return redirect_to_index_tab("chegada")


@app.route("/set-supplier", methods=["POST"])
@app.route("/set-brand", methods=["POST"])
def set_supplier():
    if not require_login():
        return redirect(url_for("login"))
    denied = require_superadm_or_redirect("index", tab="fornecedor")
    if denied:
        return denied

    clean_if_needed()
    supplier_name = request.form.get("supplier_name", "").strip()
    if not supplier_name:
        flash("Informe o fornecedor da cesta basica.", "error")
        return redirect_to_index_tab("fornecedor")

    cycle = current_cycle()
    if not cycle:
        flash("Registre primeiro o dia de chegada da cesta.", "error")
        return redirect_to_index_tab("fornecedor")

    db = get_db()
    db.execute(
        "UPDATE basket_cycles SET supplier_name = ? WHERE id = ?",
        (supplier_name, cycle["id"]),
    )
    db.commit()
    log_action("update_cycle_supplier", f"Fornecedor definido para {supplier_name}")
    flash("Fornecedor da cesta basica salvo para o ciclo mensal atual.", "success")
    return redirect_to_index_tab("fornecedor")


@app.route("/set-available-date", methods=["POST"])
def set_available_date():
    if not require_login():
        return redirect(url_for("login"))
    denied = require_superadm_or_redirect("index", tab="disponivel")
    if denied:
        return denied

    clean_if_needed()
    available_date = request.form.get("available_date", "").strip()
    try:
        datetime.strptime(available_date, "%Y-%m-%d")
    except ValueError:
        flash("Data de disponibilidade invalida.", "error")
        return redirect_to_index_tab("disponivel")

    cycle = current_cycle()
    if not cycle:
        flash("Registre primeiro o dia de chegada da cesta.", "error")
        return redirect_to_index_tab("disponivel")

    db = get_db()
    db.execute(
        "UPDATE basket_cycles SET available_date = ? WHERE id = ?",
        (available_date, cycle["id"]),
    )
    db.commit()
    log_action("update_cycle_available", f"Data disponivel definida para {available_date}")
    flash("Dia de disponibilidade salvo com sucesso.", "success")
    return redirect_to_index_tab("disponivel")


@app.route("/claim", methods=["POST"])
def claim_basket():
    if not require_login():
        return redirect(url_for("login"))

    clean_if_needed()
    cycle = current_cycle()
    if not cycle:
        flash("Defina primeiro o dia de chegada da cesta.", "error")
        return redirect_to_index_tab("retirada")
    if not cycle["available_date"]:
        flash("Defina o dia em que a cesta esta disponivel.", "error")
        return redirect_to_index_tab("retirada")

    rfid_tag = request.form.get("rfid_tag", "").strip()
    if not rfid_tag:
        flash("Informe ou leia uma tag RFID.", "error")
        return redirect_to_index_tab("retirada")

    db = get_db()
    claimant = find_claimant_by_tag(db, rfid_tag)
    if not claimant:
        flash("Cartao/tag nao cadastrado em nenhum cadastro de retirada.", "error")
        return redirect_to_index_tab("retirada")

    if claimant["source"] == "hr":
        claimed = db.execute(
            """
            SELECT c.id
            FROM claims c
            JOIN basket_cycles bc ON bc.id = c.basket_cycle_id
            WHERE c.hr_employee_id = ?
              AND strftime('%Y-%m', bc.arrival_date) = strftime('%Y-%m', ?)
            LIMIT 1
            """,
            (claimant["employee_id"], cycle["arrival_date"]),
        ).fetchone()
        claimant_name = claimant["employee_name"]
        claim_insert = (
            """
            INSERT INTO claims (employee_id, hr_employee_id, basket_cycle_id, claim_date, claim_source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                0,
                claimant["employee_id"],
                cycle["id"],
                datetime.now().isoformat(timespec="seconds"),
                "hr",
            ),
        )
    else:
        claimed = db.execute(
            """
            SELECT c.id
            FROM claims c
            JOIN basket_cycles bc ON bc.id = c.basket_cycle_id
            WHERE c.employee_id = ?
              AND strftime('%Y-%m', bc.arrival_date) = strftime('%Y-%m', ?)
            LIMIT 1
            """,
            (claimant["employee_id"], cycle["arrival_date"]),
        ).fetchone()
        claimant_name = claimant["employee_name"]
        claim_insert = (
            """
            INSERT INTO claims (employee_id, basket_cycle_id, claim_date, claim_source)
            VALUES (?, ?, ?, ?)
            """,
            (
                claimant["employee_id"],
                cycle["id"],
                datetime.now().isoformat(timespec="seconds"),
                "legacy",
            ),
        )

    if claimed:
        flash(
            f"{claimant_name} ja retirou a cesta neste mes e nao pode retirar novamente.",
            "error",
        )
        return redirect_to_index_tab("retirada")

    db.execute(claim_insert[0], claim_insert[1])
    db.commit()
    log_action("claim_basket", f"Retirada registrada para {claimant_name} ({rfid_tag})")
    flash(f"Cesta entregue para {claimant_name}.", "success")
    return redirect_to_index_tab("retirada")


@app.route("/employees", methods=["GET", "POST"])
def employees():
    if not require_login():
        return redirect(url_for("login"))

    db = get_db()
    if request.method == "POST":
        denied = require_superadm_or_redirect("employees")
        if denied:
            return denied
        registration_number = request.form.get("registration_number", "").strip()
        name = request.form.get("name", "").strip()
        rfid_tag = request.form.get("rfid_tag", "").strip()
        if not registration_number or not rfid_tag:
            flash("Matricula e tag RFID sao obrigatorios.", "error")
            return redirect(url_for("employees"))

        hr_employee = db.execute(
            """
            SELECT id, full_name
            FROM hr_employees
            WHERE registration_number = ?
            LIMIT 1
            """,
            (registration_number,),
        ).fetchone()
        if not hr_employee:
            flash("Matricula nao encontrada na base de funcionarios.", "error")
            return redirect(url_for("employees"))

        if not name:
            name = hr_employee["full_name"]
        elif normalize_text(name) != normalize_text(hr_employee["full_name"]):
            flash(
                "Nome informado diferente da matricula no banco. Use o nome oficial do cadastro.",
                "error",
            )
            return redirect(url_for("employees"))

        try:
            db.execute(
                "INSERT INTO employees (registration_number, name, rfid_tag) VALUES (?, ?, ?)",
                (registration_number, hr_employee["full_name"], rfid_tag),
            )
            db.commit()
            log_action(
                "create_server",
                f"Servidor RFID criado: mat {registration_number} / {hr_employee['full_name']} ({rfid_tag})",
            )
            flash("Servidor cadastrado com sucesso.", "success")
        except sqlite3.IntegrityError:
            flash("Matricula ou tag RFID ja cadastrada.", "error")
        return redirect(url_for("employees"))

    items = db.execute(
        """
        SELECT id, registration_number, name, rfid_tag
        FROM employees
        ORDER BY name ASC
        """
    ).fetchall()
    return render_template("employees.html", items=items)


@app.route("/funcionarios", methods=["GET", "POST"])
def funcionarios():
    if not require_login():
        return redirect(url_for("login"))

    db = get_db()
    if request.method == "POST":
        denied = require_superadm_or_redirect("funcionarios")
        if denied:
            return denied
        full_name = request.form.get("full_name", "").strip()
        registration_number = request.form.get("registration_number", "").strip()
        employment_bond_id = request.form.get("employment_bond_id", "").strip()
        department_id = request.form.get("department_id", "").strip()
        secretariat_id = request.form.get("secretariat_id", "").strip()
        job_position_id = request.form.get("job_position_id", "").strip()
        email = request.form.get("email", "").strip().lower()
        card_code = request.form.get("card_code", "").strip()

        required_fields = [
            full_name,
            employment_bond_id,
            department_id,
            secretariat_id,
            job_position_id,
            email,
            card_code,
        ]
        if not all(required_fields):
            flash("Preencha todos os campos obrigatorios do cadastro.", "error")
            return redirect(url_for("funcionarios"))

        department = db.execute(
            "SELECT id, name, secretariat_id FROM hr_departments WHERE id = ?",
            (department_id,),
        ).fetchone()
        if not department:
            flash("Lotacao invalida.", "error")
            return redirect(url_for("funcionarios"))

        if int(secretariat_id) != department["secretariat_id"]:
            flash("A lotacao informada nao pertence a secretaria selecionada.", "error")
            return redirect(url_for("funcionarios"))

        is_district_domelia = request.form.get("is_district_domelia") == "on"
        if is_domelia_department(department["name"]) or is_district_domelia:
            if not registration_number:
                flash(
                    "Para funcionarios de Domelia, a matricula deve ser informada manualmente.",
                    "error",
                )
                return redirect(url_for("funcionarios"))
            registration_source = "manual"
        else:
            if registration_number:
                registration_source = "manual"
            else:
                registration_number = generate_registration_number(db)
                registration_source = "auto"

        now = datetime.now().isoformat(timespec="seconds")
        try:
            cursor = db.execute(
                """
                INSERT INTO hr_access_cards (card_code, status, issued_at, updated_at)
                VALUES (?, 'active', ?, ?)
                """,
                (card_code, now, now),
            )
            access_card_id = cursor.lastrowid
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    registration_number,
                    full_name,
                    int(employment_bond_id),
                    department["id"],
                    int(secretariat_id),
                    int(job_position_id),
                    email,
                    access_card_id,
                    registration_source,
                    now,
                    now,
                ),
            )
            db.commit()
            log_action(
                "create_employee",
                f"Funcionario criado: {full_name} / matricula {registration_number}",
            )
            flash(
                f"Funcionario cadastrado com sucesso. Matricula: {registration_number}",
                "success",
            )
        except sqlite3.IntegrityError:
            db.rollback()
            flash(
                "Erro ao salvar. Verifique se matricula, email ou cartao ja estao cadastrados.",
                "error",
            )
        return redirect(url_for("funcionarios"))

    tab = request.args.get("tab", "todos")
    name_filter = request.args.get("nome", "").strip()
    registration_filter = request.args.get("matricula", "").strip()
    secretariat_filter = request.args.get("secretaria_id", "").strip()
    bond_filter = request.args.get("vinculo_id", "").strip()

    where_clauses = []
    params = []

    if tab in {"domelia", "domicilio"}:
        where_clauses.append("(lower(d.name) LIKE '%domelia%' OR lower(d.name) LIKE '%domicilio%')")
    elif tab == "outros":
        where_clauses.append("lower(d.name) NOT LIKE '%domelia%' AND lower(d.name) NOT LIKE '%domicilio%'")

    if name_filter:
        where_clauses.append("lower(e.full_name) LIKE ?")
        params.append(f"%{name_filter.lower()}%")
    if registration_filter:
        where_clauses.append("e.registration_number LIKE ?")
        params.append(f"%{registration_filter}%")
    if secretariat_filter:
        where_clauses.append("s.id = ?")
        params.append(secretariat_filter)
    if bond_filter:
        where_clauses.append("b.id = ?")
        params.append(bond_filter)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    total_count = db.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM hr_employees e
        JOIN hr_employment_bonds b ON b.id = e.employment_bond_id
        JOIN hr_departments d ON d.id = e.department_id
        JOIN hr_secretariats s ON s.id = e.secretariat_id
        {where_sql}
        """,
        params,
    ).fetchone()["total"]

    display_limit = 150
    query_params = params + [display_limit]
    employees_list = db.execute(
        f"""
        SELECT
            e.id,
            e.registration_number,
            e.full_name,
            b.name AS bond_name,
            d.name AS department_name,
            s.name AS secretariat_name,
            p.name AS position_name,
            e.email,
            c.card_code
        FROM hr_employees e
        JOIN hr_employment_bonds b ON b.id = e.employment_bond_id
        JOIN hr_departments d ON d.id = e.department_id
        JOIN hr_secretariats s ON s.id = e.secretariat_id
        JOIN hr_job_positions p ON p.id = e.job_position_id
        JOIN hr_access_cards c ON c.id = e.access_card_id
        {where_sql}
        ORDER BY e.full_name
        LIMIT ?
        """,
        query_params,
    ).fetchall()

    lookups = fetch_hr_lookups(db)
    selected_secretaria_id = int(secretariat_filter) if secretariat_filter.isdigit() else None
    selected_vinculo_id = int(bond_filter) if bond_filter.isdigit() else None
    return render_template(
        "funcionarios.html",
        lookups=lookups,
        employees_list=employees_list,
        total_count=total_count,
        display_limit=display_limit,
        active_tab=tab,
        filters={
            "nome": name_filter,
            "matricula": registration_filter,
            "secretaria_id": selected_secretaria_id,
            "vinculo_id": selected_vinculo_id,
        },
    )


@app.route("/users", methods=["GET", "POST"])
def users():
    if not require_login():
        return redirect(url_for("login"))
    denied = require_superadm_or_redirect("index")
    if denied:
        return denied

    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "adm").strip()
        if role not in {"adm", "superadm"}:
            role = "adm"
        if not username or not password:
            flash("Informe usuario e senha.", "error")
            return redirect(url_for("users"))
        try:
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
            db.commit()
            log_action("create_login", f"Login criado: {username} ({role})")
            flash("Login criado com sucesso.", "success")
        except sqlite3.IntegrityError:
            flash("Esse usuario ja existe.", "error")
        return redirect(url_for("users"))

    users_list = db.execute(
        "SELECT id, username, role FROM users ORDER BY username"
    ).fetchall()
    return render_template("users.html", users_list=users_list)


@app.route("/logs", methods=["GET"])
def logs():
    if not require_login():
        return redirect(url_for("login"))

    db = get_db()
    logs_list = db.execute(
        """
        SELECT username, role, action, details, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT 300
        """
    ).fetchall()
    return render_template("logs.html", logs_list=logs_list)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
