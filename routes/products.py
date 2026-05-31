from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from models import (
    add_category,
    add_product,
    delete_category,
    delete_product,
    fetch_categories,
    fetch_product,
    fetch_products,
    update_product,
)
from routes.auth import confirm_manager_pin, manager_required

products_bp = Blueprint("products", __name__, url_prefix="/products")


@products_bp.route("/")
@manager_required
def index():
    return render_template(
        "products.html",
        products=fetch_products(current_app.config["DATABASE"]),
        categories=fetch_categories(current_app.config["DATABASE"]),
        edit_product_id=request.args.get("edit", type=int),
    )


@products_bp.route("/add", methods=["POST"])
@manager_required
def add():
    add_product(
        current_app.config["DATABASE"],
        request.form["name"].strip(),
        request.form["category"].strip(),
        float(request.form["price"]),
        int(request.form["stock"]),
        int(request.form["low_stock_threshold"]),
    )
    flash("Menu item added.", "success")
    return redirect(url_for("products.index"))


@products_bp.route("/update/<int:product_id>", methods=["POST"])
@manager_required
def update(product_id: int):
    if fetch_product(current_app.config["DATABASE"], product_id) is None:
        flash("Menu item does not exist.", "error")
        return redirect(url_for("products.index"))

    update_product(
        current_app.config["DATABASE"],
        product_id,
        request.form["name"].strip(),
        request.form["category"].strip(),
        float(request.form["price"]),
        int(request.form["stock"]),
        int(request.form["low_stock_threshold"]),
    )
    flash("Menu item updated.", "success")
    return redirect(url_for("products.index"))


@products_bp.route("/delete/<int:product_id>", methods=["POST"])
@manager_required
def delete(product_id: int):
    if not confirm_manager_pin(request.form.get("manager_pin", "")):
        flash("Manager PIN is required to delete menu items.", "error")
        return redirect(url_for("products.index"))

    if delete_product(current_app.config["DATABASE"], product_id):
        flash("Menu item deleted.", "success")
    else:
        flash("Product cannot be deleted after sales have been recorded.", "error")
    return redirect(url_for("products.index"))


@products_bp.route("/categories/add", methods=["POST"])
@manager_required
def add_category_route():
    add_category(current_app.config["DATABASE"], request.form["category"].strip())
    flash("Category saved.", "success")
    return redirect(url_for("products.index"))


@products_bp.route("/categories/delete/<int:category_id>", methods=["POST"])
@manager_required
def delete_category_route(category_id: int):
    if not confirm_manager_pin(request.form.get("manager_pin", "")):
        flash("Manager PIN is required to delete categories.", "error")
        return redirect(url_for("products.index"))

    if delete_category(current_app.config["DATABASE"], category_id):
        flash("Category deleted.", "success")
    else:
        flash("Category cannot be deleted while products are linked to it.", "error")
    return redirect(url_for("products.index"))
