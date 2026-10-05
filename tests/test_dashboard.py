import json
from datetime import date

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
    assert "自主練" in html
    history_json = html.split("const attendanceHistory = ", 1)[1].split(";", 1)[0]
    attendance_history = json.loads(history_json)
    assert attendance_history
    assert all(date.fromisoformat(item["date"]).weekday() in (1, 3) for item in attendance_history)
