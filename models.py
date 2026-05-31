import re
import sqlite3
from contextlib import closing
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


def get_connection(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: str, schema_file: str | None = None) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(get_connection(database_path)) as connection:
        cursor = connection.cursor()
        cursor.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS login (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                pin_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'cashier',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS product (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0,
                low_stock_threshold INTEGER NOT NULL DEFAULT 5,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                total_amount REAL NOT NULL,
                amount_received REAL NOT NULL DEFAULT 0,
                change_amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL DEFAULT 'Cash',
                customer_name TEXT NOT NULL DEFAULT '',
                receipt_number TEXT NOT NULL DEFAULT '',
                voided INTEGER NOT NULL DEFAULT 0,
                void_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES login(id)
            );

            CREATE TABLE IF NOT EXISTS transaction_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                price_at_sale REAL NOT NULL,
                FOREIGN KEY (transaction_id) REFERENCES transactions (id),
                FOREIGN KEY (product_id) REFERENCES product (id)
            );
            """
        )
        _ensure_login_columns(connection)
        _ensure_transaction_payment_columns(connection)

        _ensure_demo_accounts(connection)

        category_count = cursor.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if category_count == 0:
            categories = extract_categories(schema_file)
            if not categories:
                categories = ["Coffee", "Tea", "Pastries", "Pasta"]
            cursor.executemany(
                "INSERT INTO categories (category) VALUES (?)",
                [(category,) for category in categories],
            )

        product_count = cursor.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        if product_count == 0:
            category_rows = cursor.execute("SELECT id, category FROM categories").fetchall()
            category_map = {row["category"]: row["id"] for row in category_rows}
            seed_products = [
                ("Espresso", "Coffee", 95.0, 30, 8),
                ("Cafe Latte", "Coffee", 155.0, 18, 5),
                ("Matcha Tea", "Tea", 140.0, 14, 4),
                ("Butter Croissant", "Pastries", 110.0, 10, 3),
                ("Creamy Carbonara", "Pasta", 210.0, 12, 4),
            ]
            cursor.executemany(
                """
                INSERT INTO product (category_id, name, price, stock, low_stock_threshold)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (category_map[category], name, price, stock, threshold)
                    for name, category, price, stock, threshold in seed_products
                    if category in category_map
                ],
            )

        _rehash_plaintext_pins(connection)
        connection.commit()


def _rehash_plaintext_pins(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT id, pin_hash FROM login").fetchall()
    for row in rows:
        pin_hash = row["pin_hash"] or ""
        if not pin_hash.startswith("pbkdf2:sha256:") and not pin_hash.startswith("scrypt:"):
            connection.execute(
                "UPDATE login SET pin_hash = ? WHERE id = ?",
                (generate_password_hash(pin_hash), row["id"]),
            )


def _ensure_login_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(login)").fetchall()
    }
    if "active" not in columns:
        connection.execute("ALTER TABLE login ADD COLUMN active INTEGER NOT NULL DEFAULT 1")


def _ensure_transaction_payment_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(transactions)").fetchall()
    }
    if "amount_received" not in columns:
        connection.execute(
            "ALTER TABLE transactions ADD COLUMN amount_received REAL NOT NULL DEFAULT 0"
        )
    if "change_amount" not in columns:
        connection.execute(
            "ALTER TABLE transactions ADD COLUMN change_amount REAL NOT NULL DEFAULT 0"
        )
    if "payment_method" not in columns:
        connection.execute(
            "ALTER TABLE transactions ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Cash'"
        )
    if "customer_name" not in columns:
        connection.execute(
            "ALTER TABLE transactions ADD COLUMN customer_name TEXT NOT NULL DEFAULT ''"
        )
    if "receipt_number" not in columns:
        connection.execute(
            "ALTER TABLE transactions ADD COLUMN receipt_number TEXT NOT NULL DEFAULT ''"
        )
    if "voided" not in columns:
        connection.execute(
            "ALTER TABLE transactions ADD COLUMN voided INTEGER NOT NULL DEFAULT 0"
        )
    if "void_reason" not in columns:
        connection.execute(
            "ALTER TABLE transactions ADD COLUMN void_reason TEXT NOT NULL DEFAULT ''"
        )


def _ensure_demo_accounts(connection: sqlite3.Connection) -> None:
    demo_accounts = [
        ("barista", "1234", "cashier"),
        ("manager", "1234", "manager"),
    ]
    for username, pin, role in demo_accounts:
        row = connection.execute(
            "SELECT id, pin_hash, role, active FROM login WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            connection.execute(
                """
                INSERT INTO login (username, pin_hash, role)
                VALUES (?, ?, ?)
                """,
                (username, generate_password_hash(pin), role),
            )
            continue

        updates = []
        params = []
        if row["role"] != role:
            updates.append("role = ?")
            params.append(role)
        if not row["active"]:
            updates.append("active = ?")
            params.append(1)

        pin_hash = row["pin_hash"] or ""
        pin_matches = (
            check_password_hash(pin_hash, pin)
            if pin_hash.startswith("pbkdf2:sha256:") or pin_hash.startswith("scrypt:")
            else pin_hash == pin
        )
        if not pin_matches:
            updates.append("pin_hash = ?")
            params.append(generate_password_hash(pin))

        if updates:
            params.append(row["id"])
            connection.execute(
                f"UPDATE login SET {', '.join(updates)} WHERE id = ?",
                params,
            )


def fetch_users(database_path: str) -> list[sqlite3.Row]:
    with closing(get_connection(database_path)) as connection:
        return connection.execute(
            """
            SELECT id, username, role, active, created_at
            FROM login
            ORDER BY role DESC, username ASC
            """
        ).fetchall()


def add_barista_account(database_path: str, username: str, pin: str) -> None:
    username = username.strip()
    pin = pin.strip()
    if not username:
        raise ValueError("Username is required.")
    if len(pin) < 4:
        raise ValueError("PIN must be at least 4 digits.")

    with closing(get_connection(database_path)) as connection:
        existing = connection.execute(
            "SELECT id FROM login WHERE lower(username) = lower(?)",
            (username,),
        ).fetchone()
        if existing:
            raise ValueError("That username already exists.")

        connection.execute(
            """
            INSERT INTO login (username, pin_hash, role)
            VALUES (?, ?, ?)
            """,
            (username, generate_password_hash(pin), "cashier"),
        )
        connection.commit()


def reset_user_pin(database_path: str, user_id: int, pin: str) -> None:
    pin = pin.strip()
    if len(pin) < 4:
        raise ValueError("PIN must be at least 4 digits.")
    with closing(get_connection(database_path)) as connection:
        row = connection.execute("SELECT id FROM login WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("Account not found.")
        connection.execute(
            "UPDATE login SET pin_hash = ? WHERE id = ?",
            (generate_password_hash(pin), user_id),
        )
        connection.commit()


def set_user_active(database_path: str, user_id: int, active: bool) -> None:
    with closing(get_connection(database_path)) as connection:
        row = connection.execute("SELECT id, role FROM login WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("Account not found.")
        if row["role"] == "manager" and not active:
            raise ValueError("Manager accounts cannot be deactivated here.")
        connection.execute(
            "UPDATE login SET active = ? WHERE id = ?",
            (1 if active else 0, user_id),
        )
        connection.commit()


def extract_categories(schema_file: str | None) -> list[str]:
    if not schema_file or not Path(schema_file).exists():
        return []
    content = Path(schema_file).read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(
        r"INSERT\s+INTO\s+categories\s*\(\s*category\s*\)\s*VALUES\s*\(\s*'([^']+)'\s*\)",
        content,
        flags=re.IGNORECASE,
    )
    return list(dict.fromkeys(matches))


def authenticate_user(database_path: str, username: str, pin: str) -> sqlite3.Row | None:
    with closing(get_connection(database_path)) as connection:
        row = connection.execute(
            """
            SELECT id, username, pin_hash, role
            FROM login
            WHERE username = ? AND active = 1
            """,
            (username,),
        ).fetchone()
        if row is None:
            return None

        pin_hash = row["pin_hash"] or ""
        if check_password_hash(pin_hash, pin):
            return row

        if pin_hash == pin:
            connection.execute(
                "UPDATE login SET pin_hash = ? WHERE id = ?",
                (generate_password_hash(pin), row["id"]),
            )
            connection.commit()
            return connection.execute(
                "SELECT id, username, pin_hash, role FROM login WHERE id = ?",
                (row["id"],),
            ).fetchone()
        return None


def fetch_categories(database_path: str) -> list[sqlite3.Row]:
    with closing(get_connection(database_path)) as connection:
        return connection.execute(
            """
            SELECT
                categories.id,
                categories.category,
                COUNT(product.id) AS product_count
            FROM categories
            LEFT JOIN product ON product.category_id = categories.id
            GROUP BY categories.id, categories.category
            ORDER BY categories.category
            """
        ).fetchall()


def ensure_category(database_path: str, category_name: str) -> int:
    with closing(get_connection(database_path)) as connection:
        row = connection.execute(
            "SELECT id FROM categories WHERE lower(category) = lower(?)",
            (category_name,),
        ).fetchone()
        if row:
            return row["id"]
        cursor = connection.execute(
            "INSERT INTO categories (category) VALUES (?)",
            (category_name,),
        )
        connection.commit()
        return cursor.lastrowid


def add_category(database_path: str, category_name: str) -> None:
    ensure_category(database_path, category_name)


def delete_category(database_path: str, category_id: int) -> bool:
    with closing(get_connection(database_path)) as connection:
        linked_products = connection.execute(
            "SELECT COUNT(*) FROM product WHERE category_id = ?",
            (category_id,),
        ).fetchone()[0]
        if linked_products:
            return False
        connection.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        connection.commit()
        return True


def fetch_products(
    database_path: str,
    category_id: int | None = None,
    search: str | None = None,
) -> list[sqlite3.Row]:
    query = """
        SELECT
            product.id,
            product.name,
            product.price,
            product.stock,
            product.low_stock_threshold,
            product.created_at,
            categories.id AS category_id,
            categories.category AS category
        FROM product
        JOIN categories ON categories.id = product.category_id
    """
    filters = []
    params: list = []
    if category_id is not None:
        filters.append("categories.id = ?")
        params.append(category_id)
    if search:
        filters.append("lower(product.name) LIKE lower(?)")
        params.append(f"%{search.strip()}%")
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY categories.category, product.name"

    with closing(get_connection(database_path)) as connection:
        return connection.execute(query, tuple(params)).fetchall()


def fetch_product(database_path: str, product_id: int) -> sqlite3.Row | None:
    with closing(get_connection(database_path)) as connection:
        return connection.execute(
            """
            SELECT
                product.id,
                product.name,
                product.price,
                product.stock,
                product.low_stock_threshold,
                categories.id AS category_id,
                categories.category AS category
            FROM product
            JOIN categories ON categories.id = product.category_id
            WHERE product.id = ?
            """,
            (product_id,),
        ).fetchone()


def add_product(
    database_path: str,
    name: str,
    category_name: str,
    price: float,
    stock: int,
    low_stock_threshold: int,
) -> None:
    category_id = ensure_category(database_path, category_name)
    with closing(get_connection(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO product (category_id, name, price, stock, low_stock_threshold)
            VALUES (?, ?, ?, ?, ?)
            """,
            (category_id, name, price, stock, low_stock_threshold),
        )
        connection.commit()


def update_product(
    database_path: str,
    product_id: int,
    name: str,
    category_name: str,
    price: float,
    stock: int,
    low_stock_threshold: int,
) -> None:
    category_id = ensure_category(database_path, category_name)
    with closing(get_connection(database_path)) as connection:
        connection.execute(
            """
            UPDATE product
            SET category_id = ?, name = ?, price = ?, stock = ?, low_stock_threshold = ?
            WHERE id = ?
            """,
            (category_id, name, price, stock, low_stock_threshold, product_id),
        )
        connection.commit()


def delete_product(database_path: str, product_id: int) -> bool:
    with closing(get_connection(database_path)) as connection:
        linked_sales = connection.execute(
            "SELECT COUNT(*) FROM transaction_items WHERE product_id = ?",
            (product_id,),
        ).fetchone()[0]
        if linked_sales:
            return False
        deleted = connection.execute("DELETE FROM product WHERE id = ?", (product_id,))
        connection.commit()
        return deleted.rowcount > 0


def create_transaction(
    database_path: str,
    user_id: int,
    items: list[dict],
    amount_received: float,
    payment_method: str,
    customer_name: str = "",
) -> int:
    total_amount = sum(item["line_total"] for item in items)
    if amount_received < total_amount:
        raise ValueError("Amount received must cover the total.")
    change_amount = amount_received - total_amount
    payment_method = payment_method.strip() or "Cash"
    customer_name = customer_name.strip()

    with closing(get_connection(database_path)) as connection:
        cursor = connection.cursor()
        for item in items:
            stock_row = cursor.execute(
                "SELECT stock, name FROM product WHERE id = ?",
                (item["product_id"],),
            ).fetchone()
            if stock_row is None:
                raise ValueError("A selected product no longer exists.")
            if stock_row["stock"] < item["quantity"]:
                raise ValueError(f"Insufficient stock for {stock_row['name']}.")

        cursor.execute(
            """
            INSERT INTO transactions (
                user_id,
                total_amount,
                amount_received,
                change_amount,
                payment_method,
                customer_name
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, total_amount, amount_received, change_amount, payment_method, customer_name),
        )
        transaction_id = cursor.lastrowid
        cursor.execute(
            "UPDATE transactions SET receipt_number = ? WHERE id = ?",
            (f"OR-{transaction_id:06d}", transaction_id),
        )
        cursor.executemany(
            """
            INSERT INTO transaction_items (transaction_id, product_id, quantity, price_at_sale)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    transaction_id,
                    item["product_id"],
                    item["quantity"],
                    item["unit_price"],
                )
                for item in items
            ],
        )
        cursor.executemany(
            """
            UPDATE product
            SET stock = stock - ?
            WHERE id = ?
            """,
            [(item["quantity"], item["product_id"]) for item in items],
        )
        connection.commit()
    return transaction_id


def void_transaction(database_path: str, transaction_id: int, reason: str) -> None:
    reason = reason.strip()
    if not reason:
        raise ValueError("Void reason is required.")

    with closing(get_connection(database_path)) as connection:
        transaction = connection.execute(
            "SELECT id, voided FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        if transaction is None:
            raise ValueError("Transaction not found.")
        if transaction["voided"]:
            raise ValueError("Transaction has already been voided.")

        items = connection.execute(
            """
            SELECT product_id, quantity
            FROM transaction_items
            WHERE transaction_id = ?
            """,
            (transaction_id,),
        ).fetchall()
        connection.executemany(
            """
            UPDATE product
            SET stock = stock + ?
            WHERE id = ?
            """,
            [(item["quantity"], item["product_id"]) for item in items],
        )
        connection.execute(
            """
            UPDATE transactions
            SET voided = 1, void_reason = ?
            WHERE id = ?
            """,
            (reason, transaction_id),
        )
        connection.commit()


def _date_filter_sql(start_date: str | None, end_date: str | None) -> tuple[str, list]:
    filters = []
    params = []
    if start_date:
        filters.append("date(transactions.created_at) >= date(?)")
        params.append(start_date)
    if end_date:
        filters.append("date(transactions.created_at) <= date(?)")
        params.append(end_date)
    if not filters:
        return "", params
    return " AND " + " AND ".join(filters), params


def fetch_recent_transactions(
    database_path: str,
    limit: int = 8,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[sqlite3.Row]:
    date_sql, params = _date_filter_sql(start_date, end_date)
    with closing(get_connection(database_path)) as connection:
        return connection.execute(
            f"""
            SELECT
                transactions.id,
                transactions.receipt_number,
                login.username,
                login.role,
                transactions.total_amount,
                transactions.amount_received,
                transactions.change_amount,
                transactions.payment_method,
                transactions.customer_name,
                transactions.voided,
                transactions.created_at
            FROM transactions
            JOIN login ON login.id = transactions.user_id
            WHERE 1 = 1 {date_sql}
            ORDER BY datetime(transactions.created_at) DESC, transactions.id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()


def fetch_transaction_detail(database_path: str, transaction_id: int) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    with closing(get_connection(database_path)) as connection:
        transaction = connection.execute(
            """
            SELECT
                transactions.id,
                transactions.receipt_number,
                transactions.total_amount,
                transactions.amount_received,
                transactions.change_amount,
                transactions.payment_method,
                transactions.customer_name,
                transactions.voided,
                transactions.void_reason,
                transactions.created_at,
                login.username,
                login.role
            FROM transactions
            JOIN login ON login.id = transactions.user_id
            WHERE transactions.id = ?
            """,
            (transaction_id,),
        ).fetchone()
        items = connection.execute(
            """
            SELECT
                product.name,
                categories.category,
                transaction_items.quantity,
                transaction_items.price_at_sale,
                transaction_items.quantity * transaction_items.price_at_sale AS line_total
            FROM transaction_items
            JOIN product ON product.id = transaction_items.product_id
            JOIN categories ON categories.id = product.category_id
            WHERE transaction_items.transaction_id = ?
            ORDER BY product.name
            """,
            (transaction_id,),
        ).fetchall()
    return transaction, items


def fetch_dashboard_stats(database_path: str) -> dict:
    with closing(get_connection(database_path)) as connection:
        stats = connection.execute(
            """
            SELECT
                COUNT(*) AS total_products,
                COALESCE(SUM(stock), 0) AS total_stock,
                SUM(CASE WHEN stock <= low_stock_threshold THEN 1 ELSE 0 END) AS low_stock_count
            FROM product
            """
        ).fetchone()
    return {
        "total_products": stats["total_products"] or 0,
        "total_stock": stats["total_stock"] or 0,
        "low_stock_count": stats["low_stock_count"] or 0,
    }


def fetch_report_summary(
    database_path: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    date_sql, params = _date_filter_sql(start_date, end_date)
    with closing(get_connection(database_path)) as connection:
        metrics = connection.execute(
            f"""
            SELECT
                COUNT(*) AS transaction_count,
                COALESCE(SUM(total_amount), 0) AS revenue,
                COALESCE(AVG(total_amount), 0) AS average_ticket,
                COALESCE(MAX(total_amount), 0) AS best_ticket
            FROM transactions
            WHERE voided = 0 {date_sql}
            """
            ,
            tuple(params),
        ).fetchone()
        top_items = connection.execute(
            f"""
            SELECT
                product.name,
                SUM(transaction_items.quantity) AS qty_sold,
                SUM(transaction_items.quantity * transaction_items.price_at_sale) AS sales
            FROM transaction_items
            JOIN transactions ON transactions.id = transaction_items.transaction_id
            JOIN product ON product.id = transaction_items.product_id
            WHERE transactions.voided = 0 {date_sql}
            GROUP BY product.id, product.name
            ORDER BY qty_sold DESC, sales DESC
            LIMIT 5
            """
            ,
            tuple(params),
        ).fetchall()
        low_stock_items = connection.execute(
            """
            SELECT
                product.name,
                categories.category,
                product.stock,
                product.low_stock_threshold
            FROM product
            JOIN categories ON categories.id = product.category_id
            WHERE product.stock <= product.low_stock_threshold
            ORDER BY product.stock ASC, product.name ASC
            """
        ).fetchall()
        category_sales = connection.execute(
            f"""
            SELECT
                categories.category,
                COALESCE(SUM(
                    CASE
                        WHEN transactions.id IS NOT NULL
                        THEN transaction_items.quantity * transaction_items.price_at_sale
                        ELSE 0
                    END
                ), 0) AS sales
            FROM categories
            LEFT JOIN product ON product.category_id = categories.id
            LEFT JOIN transaction_items ON transaction_items.product_id = product.id
            LEFT JOIN transactions ON transactions.id = transaction_items.transaction_id
                AND transactions.voided = 0 {date_sql}
            GROUP BY categories.id, categories.category
            ORDER BY sales DESC, categories.category ASC
            """
            ,
            tuple(params),
        ).fetchall()
    max_sales = max((row["sales"] for row in category_sales), default=0)
    category_chart = [
        {
            "category": row["category"],
            "sales": row["sales"] or 0,
            "percent": 0 if max_sales == 0 else round(((row["sales"] or 0) / max_sales) * 100),
        }
        for row in category_sales
    ]
    return {
        "transaction_count": metrics["transaction_count"] or 0,
        "revenue": metrics["revenue"] or 0,
        "average_ticket": metrics["average_ticket"] or 0,
        "best_ticket": metrics["best_ticket"] or 0,
        "top_items": top_items,
        "low_stock_items": low_stock_items,
        "category_chart": category_chart,
    }
