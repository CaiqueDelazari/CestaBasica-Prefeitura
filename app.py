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

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rfid_tag TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS basket_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arrival_date TEXT NOT NULL,
            available_date TEXT,
            basket_brand TEXT,
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

    admin = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123")),
        )

    if not db.execute("SELECT id FROM employees LIMIT 1").fetchone():
        demo_employees = [
            ("Maria Silva", "RFID001"),
            ("Joao Santos", "RFID002"),
            ("Ana Souza", "RFID003"),
        ]
        db.executemany(
            "INSERT INTO employees (name, rfid_tag) VALUES (?, ?)",
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
            ("Domicilio", secretariats["Assistencia Social"]),
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
        SELECT id, arrival_date, available_date, basket_brand
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


def normalize_text(value):
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").casefold()


def is_domicilio_department(department_name):
    return normalize_text(department_name) == "domicilio"


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
        SELECT c.claim_date, e.name, e.rfid_tag
        FROM claims c
        JOIN employees e ON e.id = c.employee_id
        ORDER BY c.id DESC
        LIMIT 20
        """
    ).fetchall()
    return render_template("index.html", cycle=cycle, claims=claims)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Usuario ou senha invalidos.", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/set-arrival", methods=["POST"])
def set_arrival():
    if not require_login():
        return redirect(url_for("login"))

    clean_if_needed()
    arrival_date = request.form.get("arrival_date", "").strip()
    try:
        datetime.strptime(arrival_date, "%Y-%m-%d")
    except ValueError:
        flash("Data invalida. Use o formato correto.", "error")
        return redirect(url_for("index"))

    db = get_db()
    db.execute(
        "INSERT INTO basket_cycles (arrival_date, created_at) VALUES (?, ?)",
        (arrival_date, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    flash("Dia de chegada da cesta registrado com sucesso.", "success")
    return redirect(url_for("index"))


@app.route("/set-brand", methods=["POST"])
def set_brand():
    if not require_login():
        return redirect(url_for("login"))

    clean_if_needed()
    brand = request.form.get("basket_brand", "").strip()
    if not brand:
        flash("Informe a marca da cesta basica.", "error")
        return redirect(url_for("index"))

    cycle = current_cycle()
    if not cycle:
        flash("Registre primeiro o dia de chegada da cesta.", "error")
        return redirect(url_for("index"))

    db = get_db()
    db.execute(
        "UPDATE basket_cycles SET basket_brand = ? WHERE id = ?",
        (brand, cycle["id"]),
    )
    db.commit()
    flash("Marca da cesta basica salva com sucesso.", "success")
    return redirect(url_for("index"))


@app.route("/set-available-date", methods=["POST"])
def set_available_date():
    if not require_login():
        return redirect(url_for("login"))

    clean_if_needed()
    available_date = request.form.get("available_date", "").strip()
    try:
        datetime.strptime(available_date, "%Y-%m-%d")
    except ValueError:
        flash("Data de disponibilidade invalida.", "error")
        return redirect(url_for("index"))

    cycle = current_cycle()
    if not cycle:
        flash("Registre primeiro o dia de chegada da cesta.", "error")
        return redirect(url_for("index"))

    db = get_db()
    db.execute(
        "UPDATE basket_cycles SET available_date = ? WHERE id = ?",
        (available_date, cycle["id"]),
    )
    db.commit()
    flash("Dia de disponibilidade salvo com sucesso.", "success")
    return redirect(url_for("index"))


@app.route("/claim", methods=["POST"])
def claim_basket():
    if not require_login():
        return redirect(url_for("login"))

    clean_if_needed()
    cycle = current_cycle()
    if not cycle:
        flash("Defina primeiro o dia de chegada da cesta.", "error")
        return redirect(url_for("index"))
    if not cycle["available_date"]:
        flash("Defina o dia em que a cesta esta disponivel.", "error")
        return redirect(url_for("index"))

    rfid_tag = request.form.get("rfid_tag", "").strip()
    if not rfid_tag:
        flash("Informe ou leia uma tag RFID.", "error")
        return redirect(url_for("index"))

    db = get_db()
    employee = db.execute(
        "SELECT id, name FROM employees WHERE rfid_tag = ?",
        (rfid_tag,),
    ).fetchone()
    if not employee:
        flash("Tag RFID nao cadastrada para nenhum servidor.", "error")
        return redirect(url_for("index"))

    claimed = db.execute(
        """
        SELECT c.id
        FROM claims c
        JOIN basket_cycles bc ON bc.id = c.basket_cycle_id
        WHERE c.employee_id = ?
          AND strftime('%Y-%m', bc.arrival_date) = strftime('%Y-%m', ?)
        LIMIT 1
        """,
        (employee["id"], cycle["arrival_date"]),
    ).fetchone()
    if claimed:
        flash(
            f"{employee['name']} ja retirou a cesta neste mes e nao pode retirar novamente.",
            "error",
        )
        return redirect(url_for("index"))

    db.execute(
        "INSERT INTO claims (employee_id, basket_cycle_id, claim_date) VALUES (?, ?, ?)",
        (employee["id"], cycle["id"], datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()
    flash(f"Cesta entregue para {employee['name']}.", "success")
    return redirect(url_for("index"))


@app.route("/employees", methods=["GET", "POST"])
def employees():
    if not require_login():
        return redirect(url_for("login"))

    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        rfid_tag = request.form.get("rfid_tag", "").strip()
        if not name or not rfid_tag:
            flash("Nome e tag RFID sao obrigatorios.", "error")
            return redirect(url_for("employees"))
        try:
            db.execute(
                "INSERT INTO employees (name, rfid_tag) VALUES (?, ?)",
                (name, rfid_tag),
            )
            db.commit()
            flash("Servidor cadastrado com sucesso.", "success")
        except sqlite3.IntegrityError:
            flash("Essa tag RFID ja esta cadastrada.", "error")
        return redirect(url_for("employees"))

    items = db.execute(
        "SELECT id, name, rfid_tag FROM employees ORDER BY name ASC"
    ).fetchall()
    return render_template("employees.html", items=items)


@app.route("/funcionarios", methods=["GET", "POST"])
def funcionarios():
    if not require_login():
        return redirect(url_for("login"))

    db = get_db()
    if request.method == "POST":
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

        if is_domicilio_department(department["name"]):
            if not registration_number:
                flash(
                    "Para funcionarios de Domicilio, a matricula deve ser informada manualmente.",
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

    if tab == "domicilio":
        where_clauses.append("lower(d.name) LIKE '%domicilio%'")
    elif tab == "outros":
        where_clauses.append("lower(d.name) NOT LIKE '%domicilio%'")

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
        """,
        params,
    ).fetchall()

    lookups = fetch_hr_lookups(db)
    selected_secretaria_id = int(secretariat_filter) if secretariat_filter.isdigit() else None
    selected_vinculo_id = int(bond_filter) if bond_filter.isdigit() else None
    return render_template(
        "funcionarios.html",
        lookups=lookups,
        employees_list=employees_list,
        active_tab=tab,
        filters={
            "nome": name_filter,
            "matricula": registration_filter,
            "secretaria_id": selected_secretaria_id,
            "vinculo_id": selected_vinculo_id,
        },
    )


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
