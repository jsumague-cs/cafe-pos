from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from models import add_barista_account, fetch_users, reset_user_pin, set_user_active
from routes.auth import confirm_manager_pin, manager_required

staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


@staff_bp.route("/")
@manager_required
def index():
    return render_template(
        "staff.html",
        users=fetch_users(current_app.config["DATABASE"]),
    )


@staff_bp.route("/baristas/add", methods=["POST"])
@manager_required
def add_barista():
    try:
        add_barista_account(
            current_app.config["DATABASE"],
            request.form["username"],
            request.form["pin"],
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("staff.index"))

    flash("Barista account added.", "success")
    return redirect(url_for("staff.index"))


@staff_bp.route("/<int:user_id>/pin", methods=["POST"])
@manager_required
def reset_pin(user_id: int):
    if not confirm_manager_pin(request.form.get("manager_pin", "")):
        flash("Manager PIN is required to reset a PIN.", "error")
        return redirect(url_for("staff.index"))

    try:
        reset_user_pin(
            current_app.config["DATABASE"],
            user_id,
            request.form["pin"],
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("staff.index"))

    flash("PIN reset.", "success")
    return redirect(url_for("staff.index"))


@staff_bp.route("/<int:user_id>/active", methods=["POST"])
@manager_required
def update_active(user_id: int):
    if not confirm_manager_pin(request.form.get("manager_pin", "")):
        flash("Manager PIN is required to change account status.", "error")
        return redirect(url_for("staff.index"))

    try:
        set_user_active(
            current_app.config["DATABASE"],
            user_id,
            request.form.get("active") == "1",
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("staff.index"))

    flash("Account status updated.", "success")
    return redirect(url_for("staff.index"))
