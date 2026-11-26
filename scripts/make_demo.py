"""Build a small demo repository with a mix of human- and AI-written commits.

    python scripts/make_demo.py /tmp/grokmap-demo [--with-ledger]

--with-ledger also records a few quiz results (understood, skimmed, fading) and marks
payments/ as a critical path, so the report shows every state. Used for the live demo.

Used for the README screenshots and as an end-to-end fixture. Everything is fake.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

CLAUDE = "\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
CURSOR = "\n\nCo-authored-by: Cursor Agent <cursoragent@cursor.com>\n"
COPILOT_AUTHOR = ("Copilot", "198982749+Copilot@users.noreply.github.com")


def git(repo: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env={**os.environ, **(env or {})})


def write(repo: Path, path: str, body: str) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


def commit(repo: Path, msg: str, author=("Priya Raman", "priya@example.com"), day: int = 1) -> None:
    git(repo, "add", "-A")
    when = (date(2026, 7, 1) + timedelta(days=day * 6)).isoformat() + "T10:00:00"
    env = {
        "GIT_AUTHOR_NAME": author[0],
        "GIT_AUTHOR_EMAIL": author[1],
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_NAME": author[0],
        "GIT_COMMITTER_EMAIL": author[1],
        "GIT_COMMITTER_DATE": when,
    }
    git(repo, "commit", "-q", "-m", msg, env=env)


def build(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "priya@example.com")
    git(repo, "config", "user.name", "Priya Raman")

    write(
        repo,
        "README.md",
        """
        # shopcart
        A tiny checkout service used to demo grokmap.
        """,
    )
    write(
        repo,
        "src/shopcart/cart.py",
        """
        from dataclasses import dataclass, field


        @dataclass
        class Item:
            sku: str
            name: str
            unit_price_cents: int
            quantity: int = 1

            def total(self) -> int:
                return self.unit_price_cents * self.quantity


        @dataclass
        class Cart:
            owner_id: str
            items: list[Item] = field(default_factory=list)

            def add(self, item: Item) -> None:
                for existing in self.items:
                    if existing.sku == item.sku:
                        existing.quantity += item.quantity
                        return
                self.items.append(item)

            def remove(self, sku: str) -> None:
                self.items = [i for i in self.items if i.sku != sku]

            def subtotal(self) -> int:
                return sum(i.total() for i in self.items)

            def is_empty(self) -> bool:
                return not self.items
        """,
    )
    write(
        repo,
        "src/shopcart/money.py",
        """
        def format_cents(cents: int, currency: str = "USD") -> str:
            sign = "-" if cents < 0 else ""
            cents = abs(cents)
            return f"{sign}{currency} {cents // 100}.{cents % 100:02d}"


        def split_evenly(cents: int, parts: int) -> list[int]:
            if parts <= 0:
                raise ValueError("parts must be positive")
            base, extra = divmod(cents, parts)
            return [base + (1 if i < extra else 0) for i in range(parts)]
        """,
    )
    commit(repo, "Initial cart and money helpers", day=1)

    write(
        repo,
        "src/shopcart/pricing.py",
        """
        from shopcart.cart import Cart

        TAX_RATES = {"CA": 0.0725, "NY": 0.04, "TX": 0.0625, "WA": 0.065}
        FREE_SHIPPING_OVER = 5000
        FLAT_SHIPPING = 599


        def tax_for(cart: Cart, state: str) -> int:
            rate = TAX_RATES.get(state.upper(), 0.0)
            return round(cart.subtotal() * rate)


        def shipping_for(cart: Cart) -> int:
            if cart.is_empty():
                return 0
            return 0 if cart.subtotal() >= FREE_SHIPPING_OVER else FLAT_SHIPPING


        def apply_coupon(subtotal: int, code: str | None, coupons: dict[str, dict]) -> int:
            if not code:
                return 0
            coupon = coupons.get(code.strip().upper())
            if coupon is None or coupon.get("expired"):
                return 0
            if coupon["kind"] == "percent":
                discount = subtotal * coupon["value"] // 100
            else:
                discount = coupon["value"]
            cap = coupon.get("max_cents")
            if cap is not None:
                discount = min(discount, cap)
            return min(discount, subtotal)


        def order_total(cart: Cart, state: str, coupon: str | None, coupons: dict[str, dict]) -> dict[str, int]:
            subtotal = cart.subtotal()
            discount = apply_coupon(subtotal, coupon, coupons)
            taxable = subtotal - discount
            tax = round(taxable * TAX_RATES.get(state.upper(), 0.0))
            shipping = shipping_for(cart)
            return {"subtotal": subtotal, "discount": discount, "tax": tax, "shipping": shipping,
                    "total": taxable + tax + shipping}
        """,
    )
    commit(repo, "Add pricing with tax, shipping and coupons" + CLAUDE, day=4)

    write(
        repo,
        "src/shopcart/payments/__init__.py",
        """
        from shopcart.payments.client import PaymentClient, PaymentError

        __all__ = ["PaymentClient", "PaymentError"]
        """,
    )
    write(
        repo,
        "src/shopcart/payments/client.py",
        """
        import hashlib
        import json
        import time
        import urllib.request
        from dataclasses import dataclass

        from shopcart.payments.retry import retry


        class PaymentError(Exception):
            def __init__(self, message: str, code: str | None = None, retryable: bool = False):
                super().__init__(message)
                self.code = code
                self.retryable = retryable


        @dataclass
        class Charge:
            id: str
            amount_cents: int
            status: str


        class PaymentClient:
            def __init__(self, api_key: str, base_url: str = "https://api.example-pay.com/v1", timeout: float = 10.0):
                if not api_key.startswith("sk_"):
                    raise ValueError("expected a secret key starting with sk_")
                self.api_key = api_key
                self.base_url = base_url.rstrip("/")
                self.timeout = timeout

            def idempotency_key(self, order_id: str, amount_cents: int) -> str:
                raw = f"{order_id}:{amount_cents}".encode()
                return hashlib.sha256(raw).hexdigest()[:32]

            @retry(attempts=3, base_delay=0.4, retry_on=(PaymentError,))
            def charge(self, order_id: str, amount_cents: int, token: str) -> Charge:
                if amount_cents <= 0:
                    raise PaymentError("amount must be positive", code="invalid_amount")
                body = json.dumps({"amount": amount_cents, "source": token, "metadata": {"order_id": order_id}}).encode()
                req = urllib.request.Request(
                    f"{self.base_url}/charges",
                    data=body,
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Idempotency-Key": self.idempotency_key(order_id, amount_cents),
                        "Content-Type": "application/json",
                    },
                )
                started = time.monotonic()
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        data = json.loads(resp.read())
                except urllib.error.HTTPError as exc:
                    payload = json.loads(exc.read() or b"{}")
                    code = payload.get("error", {}).get("code")
                    raise PaymentError(f"charge failed: {code}", code=code, retryable=exc.code >= 500) from exc
                except urllib.error.URLError as exc:
                    raise PaymentError("network error", retryable=True) from exc
                if time.monotonic() - started > self.timeout * 0.8:
                    # slow responses often mean the provider is degraded; surface it in logs
                    print(f"payments: slow charge for {order_id}")
                return Charge(id=data["id"], amount_cents=data["amount"], status=data["status"])

            def refund(self, charge_id: str, amount_cents: int | None = None) -> dict:
                payload = {"charge": charge_id}
                if amount_cents is not None:
                    payload["amount"] = amount_cents
                req = urllib.request.Request(
                    f"{self.base_url}/refunds",
                    data=json.dumps(payload).encode(),
                    method="POST",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read())
        """,
    )
    write(
        repo,
        "src/shopcart/payments/retry.py",
        """
        import functools
        import random
        import time


        def retry(attempts: int = 3, base_delay: float = 0.5, retry_on: tuple = (Exception,)):
            def decorator(fn):
                @functools.wraps(fn)
                def wrapper(*args, **kwargs):
                    last = None
                    for attempt in range(1, attempts + 1):
                        try:
                            return fn(*args, **kwargs)
                        except retry_on as exc:
                            if not getattr(exc, "retryable", True) or attempt == attempts:
                                raise
                            last = exc
                            delay = base_delay * (2 ** (attempt - 1))
                            time.sleep(delay + random.uniform(0, delay / 2))
                    raise last
                return wrapper
            return decorator
        """,
    )
    commit(repo, "Payments client with retries and idempotency keys" + CLAUDE, day=9)

    write(
        repo,
        "src/shopcart/api/routes.py",
        """
        import json
        from http import HTTPStatus

        from shopcart.api.auth import require_user
        from shopcart.cart import Cart, Item
        from shopcart.pricing import order_total

        CARTS: dict[str, Cart] = {}
        COUPONS = {"WELCOME10": {"kind": "percent", "value": 10, "max_cents": 2000}}


        def _json(status: HTTPStatus, body: dict) -> tuple[int, dict, str]:
            return status.value, {"Content-Type": "application/json"}, json.dumps(body)


        @require_user
        def get_cart(user_id: str, request: dict):
            cart = CARTS.get(user_id) or Cart(owner_id=user_id)
            return _json(HTTPStatus.OK, {"items": [i.__dict__ for i in cart.items], "subtotal": cart.subtotal()})


        @require_user
        def add_item(user_id: str, request: dict):
            body = request.get("json") or {}
            missing = [k for k in ("sku", "name", "unit_price_cents") if k not in body]
            if missing:
                return _json(HTTPStatus.BAD_REQUEST, {"error": f"missing fields: {', '.join(missing)}"})
            qty = int(body.get("quantity", 1))
            if qty < 1 or qty > 99:
                return _json(HTTPStatus.BAD_REQUEST, {"error": "quantity must be between 1 and 99"})
            cart = CARTS.setdefault(user_id, Cart(owner_id=user_id))
            cart.add(Item(body["sku"], body["name"], int(body["unit_price_cents"]), qty))
            return _json(HTTPStatus.CREATED, {"items": len(cart.items)})


        @require_user
        def checkout_preview(user_id: str, request: dict):
            cart = CARTS.get(user_id)
            if cart is None or cart.is_empty():
                return _json(HTTPStatus.CONFLICT, {"error": "cart is empty"})
            state = request.get("query", {}).get("state", "CA")
            coupon = request.get("query", {}).get("coupon")
            return _json(HTTPStatus.OK, order_total(cart, state, coupon, COUPONS))
        """,
    )
    write(
        repo,
        "src/shopcart/api/auth.py",
        """
        import functools
        import hmac
        import os

        SECRET = os.environ.get("SHOPCART_SECRET", "dev-secret").encode()


        def sign(user_id: str) -> str:
            mac = hmac.new(SECRET, user_id.encode(), "sha256").hexdigest()
            return f"{user_id}.{mac}"


        def verify(token: str) -> str | None:
            user_id, _, mac = token.rpartition(".")
            if not user_id:
                return None
            expected = hmac.new(SECRET, user_id.encode(), "sha256").hexdigest()
            return user_id if hmac.compare_digest(mac, expected) else None


        def require_user(handler):
            @functools.wraps(handler)
            def wrapper(request: dict):
                header = request.get("headers", {}).get("Authorization", "")
                token = header.removeprefix("Bearer ").strip()
                user_id = verify(token) if token else None
                if user_id is None:
                    return 401, {"Content-Type": "application/json"}, '{"error": "unauthorized"}'
                return handler(user_id, request)
            return wrapper
        """,
    )
    commit(repo, "Add cart API routes and token auth", author=COPILOT_AUTHOR, day=14)

    # a human fixes a bug inside AI code
    p = repo / "src/shopcart/pricing.py"
    p.write_text(
        p.read_text().replace("rate = TAX_RATES.get(state.upper(), 0.0)", "rate = TAX_RATES.get(state.strip().upper(), 0.0)")
    )
    commit(repo, "Strip whitespace from state codes", day=16)

    write(
        repo,
        "src/shopcart/reports.py",
        """
        from collections import defaultdict
        from datetime import date


        def daily_revenue(orders: list[dict]) -> dict[date, int]:
            totals: dict[date, int] = defaultdict(int)
            for order in orders:
                if order.get("status") != "paid":
                    continue
                totals[order["paid_on"]] += order["total"] - order.get("refunded", 0)
            return dict(sorted(totals.items()))


        def top_skus(orders: list[dict], n: int = 5) -> list[tuple[str, int]]:
            counts: dict[str, int] = defaultdict(int)
            for order in orders:
                for line in order.get("lines", []):
                    counts[line["sku"]] += line["quantity"]
            return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


        def refund_rate(orders: list[dict]) -> float:
            paid = [o for o in orders if o.get("status") == "paid"]
            if not paid:
                return 0.0
            refunded = sum(1 for o in paid if o.get("refunded", 0) > 0)
            return refunded / len(paid)
        """,
    )
    commit(repo, "Revenue and refund reports" + CURSOR, day=20)

    write(
        repo,
        "tests/test_money.py",
        """
        from shopcart.money import format_cents, split_evenly


        def test_format():
            assert format_cents(1234) == "USD 12.34"
            assert format_cents(-5) == "-USD 0.05"


        def test_split():
            assert split_evenly(100, 3) == [34, 33, 33]
        """,
    )
    write(
        repo,
        "tests/test_pricing.py",
        """
        from shopcart.cart import Cart, Item
        from shopcart.pricing import apply_coupon, order_total, shipping_for

        COUPONS = {"TEN": {"kind": "percent", "value": 10, "max_cents": 500}, "FIVE": {"kind": "fixed", "value": 500}}


        def make_cart(cents=1000, qty=1):
            cart = Cart("u1")
            cart.add(Item("sku-1", "Mug", cents, qty))
            return cart


        def test_coupon_cap():
            assert apply_coupon(10_000, "ten", COUPONS) == 500


        def test_coupon_never_exceeds_subtotal():
            assert apply_coupon(300, "FIVE", COUPONS) == 300


        def test_free_shipping_threshold():
            assert shipping_for(make_cart(5000)) == 0
            assert shipping_for(make_cart(4999)) == 599


        def test_total_taxes_after_discount():
            total = order_total(make_cart(10_000), "NY", "FIVE", COUPONS)
            assert total["tax"] == round(9_500 * 0.04)
        """,
    )
    commit(repo, "Add tests for money and pricing" + CLAUDE, day=22)


def add_ledger(repo: Path) -> None:
    """Record a realistic mix of quiz results so every state shows up in the report."""
    from grokmap.config import load_config
    from grokmap.ledger import Record, append_records, load_ledger
    from grokmap.quiz import mark

    (repo / ".grokmap.toml").write_text('[grokmap]\ncritical = ["src/shopcart/payments/**"]\n', encoding="utf-8")
    cfg = load_config(repo)
    mark(repo, cfg, ["src/shopcart/payments/retry.py"], 0.83, "quiz", "priya@example.com", None)
    mark(repo, cfg, ["src/shopcart/payments/client.py:1-40"], 1.0, "quiz", "priya@example.com", None)
    mark(repo, cfg, ["src/shopcart/pricing.py"], 1.0, "explain", "alex@example.com", None)
    mark(repo, cfg, ["src/shopcart/api"], 0.5, "review", "sam@example.com", None)
    mark(repo, cfg, ["tests/test_pricing.py"], 0.4, "quiz", "sam@example.com", None)
    # a pass from long ago: shows up as fading
    old = datetime.now(UTC) - timedelta(days=240)
    rec = mark(repo, cfg, ["src/shopcart/reports.py"], 0.9, "quiz", "alex@example.com", None)[0]
    lines = (repo / ".grokmap" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[:-1]
    (repo / ".grokmap" / "ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_records(repo, [Record(rec.path, rec.who, rec.score, rec.method, old, rec.hashes)])
    assert len(load_ledger(repo)) >= 6
    commit(repo, "Record grokmap quiz results", day=23)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    target = Path(args[0] if args else "/tmp/grokmap-demo")
    if target.exists() and any(target.iterdir()):
        sys.exit(f"{target} is not empty")
    build(target)
    if "--with-ledger" in sys.argv:
        add_ledger(target)
    print(f"demo repo ready at {target}")
