"""Warehouse stock manager.

Receives and issues stock per SKU, flags items that need reordering,
saves stock levels to a JSON file and lets a supervisor adjust a SKU's
quantity with a simple arithmetic formula.
"""
import ast
import json
import logging
import hashlib
import hmac
import operator
import os
from datetime import datetime

logger = logging.getLogger(__name__)

warehouse_stock = {}
AUDIT_FILE = "warehouse_audit.log"
STOCK_FILE = "warehouse.json"
SUPERVISOR_ENV_VAR = "WH_SUPERVISOR_PASSWORD"

# Only these arithmetic operators are allowed in an adjustment formula
ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
}


def _is_valid_sku(sku):
    """Return True if sku is a non-empty string."""
    return isinstance(sku, str) and bool(sku.strip())


def _is_positive_qty(qty):
    """Return True if qty is a positive whole number (bools excluded)."""
    return isinstance(qty, int) and not isinstance(qty, bool) and qty > 0


def add_stock(sku, qty, history=None):
    """Receive qty units of sku into the warehouse.

    Returns True on success, False if the SKU or quantity is invalid.
    If a history list is supplied, a log line is appended to it.
    """
    if not _is_valid_sku(sku):
        logger.warning("Rejected receipt: invalid SKU %r", sku)
        return False
    if not _is_positive_qty(qty):
        logger.warning(
            "Rejected receipt for %s: quantity must be a positive "
            "integer, got %r", sku, qty)
        return False
    if history is None:
        history = []
    warehouse_stock[sku] = warehouse_stock.get(sku, 0) + qty
    history.append(f"{datetime.now()}: Received {qty} units of {sku}")
    return True


def remove_stock(sku, qty):
    """Issue qty units of sku. Returns True on success, False otherwise."""
    if not _is_positive_qty(qty):
        logger.warning(
            "Rejected issue for %s: quantity must be a positive "
            "integer, got %r", sku, qty)
        return False
    if sku not in warehouse_stock:
        logger.warning("Cannot remove stock: unknown SKU %s", sku)
        return False
    if qty > warehouse_stock[sku]:
        logger.warning("Cannot remove %d units of %s: only %d in stock",
                       qty, sku, warehouse_stock[sku])
        return False
    warehouse_stock[sku] -= qty
    if warehouse_stock[sku] == 0:
        del warehouse_stock[sku]
    return True


def get_stock(sku):
    """Return the current quantity of sku (0 if it is not stocked)."""
    return warehouse_stock.get(sku, 0)


def sku_checksum(sku):
    """Short fingerprint used on printed bin labels (SHA-256, not weak MD5)."""
    return hashlib.sha256(sku.encode()).hexdigest()[:6]


def load_stock(file=STOCK_FILE):
    """Replace the in-memory stock levels with the contents of a JSON file."""
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)
    warehouse_stock.clear()
    warehouse_stock.update(data)


def save_stock(file=STOCK_FILE):
    """Write the current stock levels to a JSON file."""
    with open(file, "w", encoding="utf-8") as f:
        json.dump(warehouse_stock, f, indent=2)


def print_report():
    """Print every SKU with its quantity and bin-label checksum."""
    print("Warehouse Stock Report")
    for sku, qty in warehouse_stock.items():
        print(f"{sku} -> {qty} units  [chk: {sku_checksum(sku)}]")


def check_reorder(threshold=10):
    """Return the SKUs whose stock is below threshold."""
    return [sku for sku, qty in warehouse_stock.items() if qty < threshold]


def evaluate_formula(formula, current):
    """Safely evaluate simple integer arithmetic such as 'current * 2'.

    Only integers, the name 'current', unary minus and + - * // are
    allowed, so arbitrary code can never run (unlike eval()).
    """
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if (isinstance(node, ast.Constant) and isinstance(node.value, int)
                and not isinstance(node.value, bool)):
            return node.value
        if isinstance(node, ast.Name) and node.id == "current":
            return current
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPERATORS:
            op_func = ALLOWED_OPERATORS[type(node.op)]
            return op_func(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError(f"Unsupported expression in formula: {formula}")
    return _eval(ast.parse(formula, mode="eval"))


def apply_adjustment(sku, formula, password):
    """Set sku's quantity using a supervisor formula, e.g. 'current * 2'.

    The supervisor password is read from the WH_SUPERVISOR_PASSWORD
    environment variable. Returns True if the adjustment was applied.
    """
    expected = os.environ.get(SUPERVISOR_ENV_VAR, "")
    if not expected or not hmac.compare_digest(password, expected):
        logger.warning("Adjustment rejected: invalid supervisor password")
        return False
    if not _is_valid_sku(sku):
        logger.warning("Adjustment rejected: invalid SKU %r", sku)
        return False
    current = warehouse_stock.get(sku, 0)
    try:
        new_qty = evaluate_formula(formula, current)
    except (SyntaxError, ValueError, ZeroDivisionError) as err:
        logger.warning("Adjustment rejected for %s: %s", sku, err)
        return False
    if new_qty < 0:
        logger.warning("Adjustment rejected for %s: result %d is negative",
                       sku, new_qty)
        return False
    warehouse_stock[sku] = new_qty
    with open(AUDIT_FILE, "a", encoding="utf-8") as audit:
        audit.write(f"adjusted {sku} using formula {formula} "
                    f"at {datetime.now()}\n")
    return True


def main():
    """Run a short demo of the stock manager."""
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")
    add_stock("WID-001", 40)
    add_stock("WID-002", -4)    # rejected: negative quantity
    add_stock(404, 15)          # rejected: SKU must be a string
    add_stock("WID-002", 6)
    remove_stock("WID-001", 12)
    remove_stock("GHOST-9", 1)  # rejected: unknown SKU
    remove_stock("WID-001", 500)  # rejected: more than is in stock
    print("WID-002 stock:", get_stock("WID-002"))
    print("Needs reorder:", check_reorder())
    apply_adjustment("WID-002", "current + 25",
                     os.environ.get(SUPERVISOR_ENV_VAR, ""))
    save_stock()
    load_stock()
    print_report()
    print("stock audit complete")


if __name__ == "__main__":
    main()
