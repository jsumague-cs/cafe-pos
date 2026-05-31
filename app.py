from flask import Flask, redirect, url_for

from config import Config
from models import initialize_database
from routes.auth import auth_bp
from routes.pos import pos_bp
from routes.products import products_bp
from routes.reports import reports_bp
from routes.staff import staff_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    initialize_database(app.config["DATABASE"], app.config["SCHEMA_FILE"])

    app.register_blueprint(auth_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(staff_bp)

    @app.route("/")
    def index():
        return redirect(url_for("pos.dashboard"))

    @app.route("/login")
    def login_shortcut():
        return redirect(url_for("auth.login"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
