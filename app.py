import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

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


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
