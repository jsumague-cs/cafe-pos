from datetime import date, timedelta

from flask import Blueprint, current_app, render_template, request

from models import fetch_recent_transactions, fetch_report_summary
from routes.auth import manager_required

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
@manager_required
def index():
    preset = request.args.get("preset", "")
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    if preset == "today":
        today = date.today().isoformat()
        start_date = today
        end_date = today
    elif preset == "week":
        today = date.today()
        start_date = (today - timedelta(days=6)).isoformat()
        end_date = today.isoformat()

    return render_template(
        "reports.html",
        summary=fetch_report_summary(current_app.config["DATABASE"], start_date, end_date),
        recent_transactions=fetch_recent_transactions(
            current_app.config["DATABASE"],
            limit=15,
            start_date=start_date,
            end_date=end_date,
        ),
        filters={
            "preset": preset,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
