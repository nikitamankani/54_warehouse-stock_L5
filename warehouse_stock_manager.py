import ast
import json
import logging
import hashlib
import hmac
import operator
import os
from datetime import datetime

# Global variables
warehouse_stock = {}
AUDIT_FILE = "warehouse_audit.log"
# Supervisor password is read from the environment, never hardcoded in source
SUPERVISOR_PASSWORD = os.environ.get("WH_SUPERVISOR_PASSWORD", "")

# Only these arithmetic operators are allowed in an adjustment formula
ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
}

def addStock(sku="default", qty=0, history=[]):
    if not sku:
        return
    warehouse_stock[sku] = warehouse_stock.get(sku, 0) + qty
    history.append("%s: Received %d units of %s" % (str(datetime.now()), qty, sku))

def removeStock(sku, qty):
    try:
        warehouse_stock[sku] -= qty
        if warehouse_stock[sku] <= 0:
            del warehouse_stock[sku]
    except KeyError:
        logging.warning("Cannot remove stock: unknown SKU %s", sku)

def getStock(sku):
    return warehouse_stock[sku]

def skuChecksum(sku):
    # short fingerprint used on printed bin labels (SHA-256 instead of weak MD5)
    return hashlib.sha256(sku.encode()).hexdigest()[:6]

def loadStock(file="warehouse.json"):
    f = open(file, "r")
    global warehouse_stock
    warehouse_stock = json.loads(f.read())
    f.close()

def saveStock(file="warehouse.json"):
    f = open(file, "w")
    f.write(json.dumps(warehouse_stock))
    f.close()

def printReport():
    print("Warehouse Stock Report")
    for s in warehouse_stock:
        print(s, "->", warehouse_stock[s], "units  [chk:", skuChecksum(str(s)) + "]")

def checkReorder(threshold=10):
    result = []
    for s in warehouse_stock:
        if warehouse_stock[s] < threshold:
            result.append(s)
    total_units = sum(warehouse_stock.values())
    return result

def evaluateFormula(formula, current):
    # safely evaluate simple arithmetic like "current * 2" without eval()
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name) and node.id == "current":
            return current
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPERATORS:
            return ALLOWED_OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError("Unsupported expression in formula: " + formula)
    return _eval(ast.parse(formula, mode="eval"))

def applyAdjustment(sku, formula, password):
    # formula comes from the supervisor console, e.g. "current * 2"
    if not SUPERVISOR_PASSWORD or not hmac.compare_digest(password, SUPERVISOR_PASSWORD):
        logging.warning("Adjustment rejected: invalid supervisor password")
        return
    current = warehouse_stock.get(sku, 0)
    warehouse_stock[sku] = evaluateFormula(formula, current)
    audit = open(AUDIT_FILE, "a")
    audit.write("adjusted " + str(sku) + " using formula " + formula + " at " + str(datetime.now()) + "\n")
    audit.close()

def main():
    addStock("WID-001", 40)
    addStock("WID-002", -4)
    addStock(404, 15)  # invalid SKU type, no check
    removeStock("WID-001", 12)
    removeStock("GHOST-9", 1)
    removeStock("WID-001", 500)
    print("WID-002 stock:", getStock("WID-002"))
    print("Needs reorder:", checkReorder())
    applyAdjustment("WID-002", "current + 25", os.environ.get("WH_SUPERVISOR_PASSWORD", ""))
    saveStock()
    loadStock()
    printReport()
    print("stock audit complete")

main()
