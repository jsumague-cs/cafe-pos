from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from models import (
    create_transaction,
    fetch_categories,
    fetch_dashboard_stats,
    fetch_product,
    fetch_products,
    fetch_recent_transactions,
    fetch_transaction_detail,
    void_transaction,
)
from routes.auth import confirm_manager_pin, login_required, manager_required

pos_bp = Blueprint("pos", __name__, url_prefix="/pos")


def _remember_pos_url() -> None:
    query = {}
    category = request.args.get("category", type=int)
    search = request.args.get("q", "").strip()
    if category:
        query["category"] = category
    if search:
        query["q"] = search
    session["last_pos_url"] = url_for("pos.dashboard", **query)


def _pos_return_url() -> str:
    return session.get("last_pos_url", url_for("pos.dashboard"))


@pos_bp.route("/")
@login_required
def dashboard():
    category_id = request.args.get("category", type=int)
    search = request.args.get("q", "").strip()
    _remember_pos_url()
    cart = session.get("cart", [])
    return render_template(
        "pos.html",
        products=fetch_products(current_app.config["DATABASE"], category_id, search),
        categories=fetch_categories(current_app.config["DATABASE"]),
        selected_category=category_id,
        search=search,
        recent_transactions=fetch_recent_transactions(current_app.config["DATABASE"]),
        cart=cart,
        cart_total=sum(item["line_total"] for item in cart),
        stats=fetch_dashboard_stats(current_app.config["DATABASE"]),
    )


@pos_bp.route("/cart/add", methods=["POST"])
@login_required
def add_to_cart():
    product_id = int(request.form["product_id"])
    quantity = max(int(request.form.get("quantity", 1)), 1)
    product = fetch_product(current_app.config["DATABASE"], product_id)
    if product is None:
        flash("Selected menu item was not found.", "error")
        return redirect(_pos_return_url())
    if product["stock"] < quantity:
        flash("Not enough stock for that quantity.", "error")
        return redirect(_pos_return_url())

    cart = session.get("cart", [])
    for item in cart:
        if item["product_id"] == product_id:
            new_qty = item["quantity"] + quantity
            if new_qty > product["stock"]:
                flash("Cart quantity exceeds available stock.", "error")
                return redirect(_pos_return_url())
            item["quantity"] = new_qty
            item["line_total"] = item["quantity"] * item["unit_price"]
            session["cart"] = cart
            flash(f"Updated {product['name']} quantity.", "success")
            return redirect(_pos_return_url())

    cart.append(
        {
            "product_id": product["id"],
            "name": product["name"],
            "quantity": quantity,
            "unit_price": float(product["price"]),
            "line_total": quantity * float(product["price"]),
            "stock": product["stock"],
        }
    )
    session["cart"] = cart
    flash(f"Added {product['name']} to the cart.", "success")
    return redirect(_pos_return_url())


@pos_bp.route("/cart/remove/<int:product_id>", methods=["POST"])
@login_required
def remove_from_cart(product_id: int):
    cart = [item for item in session.get("cart", []) if item["product_id"] != product_id]
    session["cart"] = cart
    flash("Item removed from the cart.", "success")
    return redirect(_pos_return_url())


@pos_bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart = session.get("cart", [])
    if not cart:
        flash("Add items before checkout.", "error")
        return redirect(_pos_return_url())

    try:
        amount_received = float(request.form.get("amount_received", 0))
        transaction_id = create_transaction(
            current_app.config["DATABASE"],
            session["user"]["id"],
            cart,
            amount_received,
            request.form.get("payment_method", "Cash"),
            request.form.get("customer_name", ""),
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(_pos_return_url())

    session["cart"] = []
    flash(f"Transaction #{transaction_id} has been completed.", "success")
    return redirect(url_for("pos.transaction_detail", transaction_id=transaction_id))


@pos_bp.route("/transactions/<int:transaction_id>")
@login_required
def transaction_detail(transaction_id: int):
    transaction, items = fetch_transaction_detail(current_app.config["DATABASE"], transaction_id)
    if transaction is None:
        flash("Transaction not found.", "error")
        return redirect(_pos_return_url())
    return render_template(
        "transaction_detail.html",
        transaction=transaction,
        items=items,
        shop_name=current_app.config["SHOP_NAME"],
        bir_registration=current_app.config["SHOP_BIR_REGISTRATION"],
        return_to_pos=_pos_return_url(),
    )


@pos_bp.route("/transactions/<int:transaction_id>/void", methods=["POST"])
@manager_required
def void(transaction_id: int):
    if not confirm_manager_pin(request.form.get("manager_pin", "")):
        flash("Manager PIN is required to void transactions.", "error")
        return redirect(url_for("pos.transaction_detail", transaction_id=transaction_id))

    try:
        void_transaction(
            current_app.config["DATABASE"],
            transaction_id,
            request.form.get("reason", ""),
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("pos.transaction_detail", transaction_id=transaction_id))

    flash(f"Transaction #{transaction_id} has been voided and stock was restored.", "success")
    return redirect(url_for("pos.transaction_detail", transaction_id=transaction_id))
