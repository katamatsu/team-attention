import os
import sqlite3
from datetime import date, timedelta
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
            location TEXT NOT NULL
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
            db.execute("INSERT OR REPLACE INTO attendance (member_id, practice_id, status) VALUES (?, ?, 'present')", (member_id, practice_id))
            db.commit()
            flash("出席を登録しました。", "success")
        return redirect(url_for("dashboard", selected=request.form.get("selected", "")))

    practices = db.execute("SELECT * FROM practices ORDER BY practice_date DESC").fetchall()
    selected = request.args.get("selected") or (practices[0]["practice_date"] if practices else "")
    practice = next((item for item in practices if item["practice_date"] == selected), practices[0] if practices else None)
    members = db.execute(
        """
        SELECT m.*, a.status FROM members m
        LEFT JOIN attendance a ON a.member_id = m.id AND a.practice_id = ?
        ORDER BY CAST(REPLACE(m.number, '#', '') AS INTEGER)
        """,
        (practice["id"],) if practice else (0,),
    ).fetchall()
    present_count = sum(member["status"] == "present" for member in members)
    return render_template("dashboard.html", practices=practices, practice=practice, members=members, present_count=present_count)


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
