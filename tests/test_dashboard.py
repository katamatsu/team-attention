import json
from datetime import date

import app as app_module
from app import app


app.config["TESTING"] = True


def test_dashboard_has_attendance_chart_and_weekend_self_training_label():
    client = app.test_client()
    response = client.get("/?month=2026-10")
    html = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "出席人数" in html
    assert "部活動の活動日" in html
    assert "type: 'line'" in html
    assert "max: 22" in html
    assert "自主練" in html
    history_json = html.split("const attendanceHistory = ", 1)[1].split(";", 1)[0]
    attendance_history = json.loads(history_json)
    assert attendance_history
    assert all(date.fromisoformat(item["date"]).weekday() in (1, 3) for item in attendance_history)


def test_game_list_shows_team_score_before_opponent_score(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DATABASE", tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DATABASE_URL", None)
    client = app.test_client()
    assert client.get("/stats").status_code == 200

    with app.app_context():
        db = app_module.get_db()
        game_id = db.execute(
            "INSERT INTO games (game_date, opponent, location) VALUES (%s, %s, %s)",
            ("2026-10-01", "相手A", "体育館"),
        ).lastrowid
        member_id = db.execute("SELECT id FROM members LIMIT 1").fetchone()["id"]
        db.execute(
            "INSERT INTO game_stats (game_id, member_id, two_pm, three_pm, free_throw_m) VALUES (%s, %s, %s, %s, %s)",
            (game_id, member_id, 3, 1, 2),
        )
        opponent_player_id = db.execute(
            "INSERT INTO opponent_players (game_id, number) VALUES (%s, %s)",
            (game_id, "#9"),
        ).lastrowid
        db.execute(
            "INSERT INTO opponent_stats (game_id, opponent_player_id, two_pm) VALUES (%s, %s, %s)",
            (game_id, opponent_player_id, 2),
        )
        db.commit()

    response = client.get(f"/stats?game={game_id}&side=opponent")
    html = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "最終スコア 11対4" in html
