from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from models import authenticate_user

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def manager_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if session["user"]["role"] != "manager":
            flash("Manager access is required for that page.", "error")
            return redirect(url_for("pos.dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def confirm_manager_pin(pin: str) -> bool:
    if session.get("user", {}).get("role") != "manager":
        return False
    user = authenticate_user(
        current_app.config["DATABASE"],
        session["user"]["username"],
        pin.strip(),
    )
    return user is not None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        session.clear()

    if request.method == "POST":
        user = authenticate_user(
            current_app.config["DATABASE"],
            request.form["username"].strip(),
            request.form["pin"].strip(),
        )
        if user:
            session["user"] = {
                "id": user["id"],
                "username": user["username"],
                "display_name": user["username"].title(),
                "role": user["role"],
            }
            flash("Welcome back to the cafe POS.", "success")
            return redirect(url_for("pos.dashboard"))
        flash("Invalid username or PIN.", "error")
    return render_template("login.html")


@auth_bp.route("/demo/manager", methods=["POST"])
def demo_manager_login():
    user = authenticate_user(current_app.config["DATABASE"], "manager", "1234")
    if user is None:
        flash("Demo manager account is not available. Restart the app and try again.", "error")
        return redirect(url_for("auth.login"))

    session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "display_name": "Demo Manager",
        "role": user["role"],
    }
    flash("Signed in as demo manager. Menu and reports are now available.", "success")
    return redirect(url_for("pos.dashboard"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))
