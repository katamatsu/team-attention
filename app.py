import os
import sqlite3
import calendar
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "attendance.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-this")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            number TEXT NOT NULL,
            position TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS practices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            practice_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            location TEXT NOT NULL,
            is_cancelled INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            practice_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'present',
            UNIQUE(member_id, practice_id),
            FOREIGN KEY(member_id) REFERENCES members(id),
            FOREIGN KEY(practice_id) REFERENCES practices(id)
        );
        """
    )
    columns = {row[1] for row in db.execute("PRAGMA table_info(practices)").fetchall()}
    if "is_cancelled" not in columns:
        db.execute("ALTER TABLE practices ADD COLUMN is_cancelled INTEGER NOT NULL DEFAULT 0")
    if db.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO members (name, number, position) VALUES (?, ?, ?)",
            [("山田 太郎", "#4", "G"), ("佐藤 花子", "#7", "F"), ("鈴木 一郎", "#10", "G"), ("高橋 翼", "#12", "C"), ("伊藤 美咲", "#15", "F")],
        )
    if db.execute("SELECT COUNT(*) FROM practices").fetchone()[0] == 0:
        today = date.today()
        db.executemany(
            "INSERT INTO practices (practice_date, start_time, location) VALUES (?, ?, ?)",
            [((today - timedelta(days=offset)).isoformat(), time, "第一体育館") for offset, time in [(0, "18:30"), (1, "18:30"), (3, "19:00"), (5, "18:30"), (7, "19:00")]],
        )
    db.commit()


def practice_rule(day):
    if day.weekday() == 1:
        return "17:00", "19:00"
    if day.weekday() == 3:
        return "18:00", "20:00"
    if day.weekday() == 5 and ((day.day - 1) // 7 + 1) in (2, 4, 5):
        return "17:00", "20:00"
    if day.weekday() == 6:
        return "10:00", "13:00"
    return None


def ensure_month_practices(year, month):
    db = get_db()
    last_day = calendar.monthrange(year, month)[1]
    for day_number in range(1, last_day + 1):
        practice_day = date(year, month, day_number)
        rule = practice_rule(practice_day)
        if rule is None:
            continue
        exists = db.execute("SELECT id FROM practices WHERE practice_date = ?", (practice_day.isoformat(),)).fetchone()
        if exists is None:
            db.execute("INSERT INTO practices (practice_date, start_time, location) VALUES (?, ?, ?)", (practice_day.isoformat(), f"{rule[0]} - {rule[1]}", "第一体育館"))
        else:
            current = db.execute("SELECT start_time FROM practices WHERE id = ?", (exists["id"],)).fetchone()
            if " - " not in current["start_time"]:
                db.execute("UPDATE practices SET start_time = ? WHERE id = ?", (f"{rule[0]} - {rule[1]}", exists["id"]))
    db.commit()


@app.before_request
def load_user_and_database():
    init_db()


@app.route("/", methods=("GET", "POST"))
def dashboard():
    db = get_db()
    if request.method == "POST":
        member_id = request.form.get("member_id", type=int)
        practice_id = request.form.get("practice_id", type=int)
        if member_id and practice_id:
            practice_status = db.execute("SELECT is_cancelled FROM practices WHERE id = ?", (practice_id,)).fetchone()
            if practice_status and practice_status["is_cancelled"]:
                flash("休止中の練習には出席を登録できません。", "error")
                return redirect(url_for("dashboard", selected=request.form.get("selected", ""), month=request.form.get("month", "")))
            db.execute("INSERT OR REPLACE INTO attendance (member_id, practice_id, status) VALUES (?, ?, 'present')", (member_id, practice_id))
            db.commit()
            flash("出席を登録しました。", "success")
        return redirect(url_for("dashboard", selected=request.form.get("selected", ""), month=request.form.get("month", "")))

    today = date.today()
    try:
        month_date = datetime.strptime(request.args.get("month", today.strftime("%Y-%m")), "%Y-%m").date().replace(day=1)
    except ValueError:
        month_date = today.replace(day=1)
    ensure_month_practices(month_date.year, month_date.month)
    practices = db.execute("SELECT * FROM practices WHERE practice_date LIKE ? ORDER BY practice_date", (f"{month_date:%Y-%m}%",)).fetchall()
    selected = request.args.get("selected") or (today.isoformat() if any(item["practice_date"] == today.isoformat() for item in practices) else (practices[0]["practice_date"] if practices else ""))
    practice = next((item for item in practices if item["practice_date"] == selected), None)
    members = db.execute(
        """
        SELECT m.*, a.status FROM members m
        LEFT JOIN attendance a ON a.member_id = m.id AND a.practice_id = ?
        ORDER BY CAST(REPLACE(m.number, '#', '') AS INTEGER)
        """,
        (practice["id"],) if practice else (0,),
    ).fetchall()
    present_count = sum(member["status"] == "present" for member in members) if practice else 0
    previous_month = (month_date - timedelta(days=1)).replace(day=1)
    next_month = (month_date + timedelta(days=32)).replace(day=1)
    calendar_days = calendar.Calendar(firstweekday=6).monthdatescalendar(month_date.year, month_date.month)
    practice_by_date = {item["practice_date"]: item for item in practices}
    return render_template("dashboard.html", practices=practices, practice=practice, selected=selected, members=members, present_count=present_count, calendar_days=calendar_days, practice_by_date=practice_by_date, month_date=month_date, previous_month=previous_month, next_month=next_month)


@app.route("/practices/<int:practice_id>/toggle", methods=("POST",))
def toggle_practice(practice_id):
    db = get_db()
    db.execute("UPDATE practices SET is_cancelled = CASE is_cancelled WHEN 1 THEN 0 ELSE 1 END WHERE id = ?", (practice_id,))
    db.commit()
    flash("練習予定を更新しました。", "success")
    return redirect(url_for("dashboard", selected=request.form.get("selected", ""), month=request.form.get("month", "")))


@app.route("/practices/new", methods=("GET", "POST"))
def add_practice():
    if request.method == "POST":
        practice_date = request.form.get("practice_date", "")
        start_time = request.form.get("start_time", "").strip()
        end_time = request.form.get("end_time", "").strip()
        location = request.form.get("location", "第一体育館").strip()
        try:
            datetime.strptime(practice_date, "%Y-%m-%d")
            if not start_time or not end_time or not location:
                raise ValueError
        except ValueError:
            flash("日付、時間、場所を正しく入力してください。", "error")
        else:
            db = get_db()
            existing = db.execute("SELECT id FROM practices WHERE practice_date = ?", (practice_date,)).fetchone()
            if existing:
                db.execute("UPDATE practices SET start_time = ?, location = ?, is_cancelled = 0 WHERE id = ?", (f"{start_time} - {end_time}", location, existing["id"]))
            else:
                db.execute("INSERT INTO practices (practice_date, start_time, location) VALUES (?, ?, ?)", (practice_date, f"{start_time} - {end_time}", location))
            db.commit()
            flash("練習予定を追加しました。", "success")
            return redirect(url_for("dashboard", selected=practice_date, month=practice_date[:7]))
    return render_template("add_practice.html")


@app.route("/members/<int:member_id>/edit", methods=("GET", "POST"))
def edit_member(member_id):
    db = get_db()
    member = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if member is None:
        return "メンバーが見つかりません", 404
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        number = request.form.get("number", "").strip()
        if not name or not number:
            flash("名前と背番号を入力してください。", "error")
        else:
            db.execute("UPDATE members SET name = ?, number = ? WHERE id = ?", (name, number, member_id))
            db.commit()
            flash("名前を更新しました。", "success")
            return redirect(url_for("dashboard"))
    return render_template("edit_member.html", member=member)


@app.route("/members/new", methods=("GET", "POST"))
def add_member():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        number = request.form.get("number", "").strip()
        position = request.form.get("position", "").strip().upper()
        if not name or not number or not position:
            flash("名前、背番号、ポジションを入力してください。", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO members (name, number, position) VALUES (?, ?, ?)", (name, number, position))
            db.commit()
            flash("メンバーを追加しました。", "success")
            return redirect(url_for("dashboard"))
    return render_template("add_member.html")


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
