# MEMORIA: создание оплаты в Точке (функция Яндекс Облака, Python 3.12, без библиотек)
# Переменные окружения: TOCHKA_JWT (ключ Точки, обязательно),
#   CUSTOMER_CODE и MERCHANT_ID (необязательно: если пусто, узнаём сами).
import json, os, re, time, urllib.request, urllib.error

API = "https://enter.tochka.com/uapi"
SITE = "https://memoria-jewelry.ru"
ORIGINS = {SITE, "https://www.memoria-jewelry.ru"}
PROMO = {"MEMORIA10": 0.10}          # скидка только на украшения, не на сертификаты
MIN_CERT, MAX_CERT = 1000, 100000
_cache = {}

def _req(url, data=None, auth=True):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth:
        h["Authorization"] = "Bearer " + os.environ["TOCHKA_JWT"].strip()
    r = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                               headers=h, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=20) as f:
            return json.loads(f.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print("TOCHKA ERROR", e.code, url, body[:2000])
        raise RuntimeError("tochka %s" % e.code)

def _ids():
    cc = os.environ.get("CUSTOMER_CODE") or _cache.get("cc")
    if not cc:
        cs = _req(API + "/open-banking/v1.0/customers")["Data"]["Customer"]
        cc = next(c["customerCode"] for c in cs if c.get("customerType") == "Business")
        _cache["cc"] = cc
        print("customerCode", cc)
    mid = os.environ.get("MERCHANT_ID") or _cache.get("mid")
    if not mid:
        rs = _req(API + "/acquiring/v1.0/retailers?customerCode=" + cc)["Data"]["Retailer"]
        print("retailers", json.dumps(rs, ensure_ascii=False)[:1500])
        mid = next((r.get("merchantId") for r in rs if r.get("merchantId") and r.get("status") in (None, "REG", "ACTIVE", "active")), None) \
              or next(r.get("merchantId") for r in rs if r.get("merchantId"))
        _cache["mid"] = mid
    return cc, mid

def _prices():
    p = _cache.get("prices")
    if not p or time.time() - p[0] > 300:
        with urllib.request.urlopen(SITE + "/prices.json?t=%d" % time.time(), timeout=10) as f:
            p = (time.time(), json.loads(f.read().decode()))
        _cache["prices"] = p
    return p[1]

def _cors(origin):
    o = origin if origin in ORIGINS else SITE
    return {"Access-Control-Allow-Origin": o, "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin",
            "Content-Type": "application/json; charset=utf-8"}

def _out(code, obj, origin):
    return {"statusCode": code, "headers": _cors(origin), "body": json.dumps(obj, ensure_ascii=False)}

def build_order(body, prices):
    """Проверяет корзину и считает суммы по ценам с сайта, а не из браузера."""
    disc = PROMO.get(str(body.get("promo", "")).strip().upper(), 0)
    items, skus = [], []
    for x in body.get("items", [])[:30]:
        sku, q = str(x.get("sku", "")), int(x.get("q", 0))
        if not 1 <= q <= 20:
            raise ValueError("Неверное количество")
        m = re.fullmatch(r"CERT-(\d+)-([EP])", sku)
        if m:
            n = int(m.group(1))
            if not MIN_CERT <= n <= MAX_CERT:
                raise ValueError("Неверная сумма сертификата")
            items.append({"name": "Подарочный сертификат MEMORIA на %d руб." % n, "amount": n,
                          "quantity": q, "paymentMethod": "advance", "paymentObject": "payment",
                          "vatType": "none", "measure": "шт."})
            skus.append("сертификат %d" % n)
            continue
        it = prices.get(sku)
        if not it:
            raise ValueError("Нет такого украшения: " + sku)
        price = round(it["price"] * (1 - disc), 2)
        items.append({"name": (it["name"] + " " + sku)[:128], "amount": price, "quantity": q,
                      "paymentMethod": "full_payment", "paymentObject": "goods",
                      "vatType": "none", "measure": "шт."})
        skus.append(sku + (" x%d" % q if q > 1 else ""))
    if not items:
        raise ValueError("Корзина пуста")
    total = round(sum(i["amount"] * i["quantity"] for i in items), 2)
    return items, skus, total

def handler(event, context):
    h = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    origin = h.get("origin", "")
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": _cors(origin), "body": ""}
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64; raw = base64.b64decode(raw).decode()
        body = json.loads(raw)
        email = str(body.get("email", "")).strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 100:
            return _out(400, {"error": "Укажите почту для чека"}, origin)
        mode = "card" if body.get("mode") == "card" else "sbp"
        items, skus, total = build_order(body, _prices())
    except ValueError as e:
        return _out(400, {"error": str(e)}, origin)
    except Exception as e:
        print("BAD REQUEST", repr(e))
        return _out(400, {"error": "Не удалось прочитать заказ"}, origin)
    try:
        cc, mid = _ids()
        order = time.strftime("%d%m-%H%M%S", time.gmtime(time.time() + 3 * 3600))
        data = {"customerCode": cc, "merchantId": mid, "amount": total,
                "purpose": ("Заказ %s с сайта MEMORIA: %s" % (order, ", ".join(skus)))[:140],
                "paymentMode": [mode],
                "redirectUrl": SITE + "/?oplata=ok&z=" + order,
                "failRedirectUrl": SITE + "/?oplata=fail",
                "Client": {"email": email},
                "Items": items}
        r = _req(API + "/acquiring/v1.0/payments_with_receipt", {"Data": data})["Data"]
        print("ORDER", order, total, r.get("operationId"))
        return _out(200, {"url": r["paymentLink"], "order": order, "total": total}, origin)
    except Exception as e:
        print("PAY ERROR", repr(e))
        return _out(502, {"error": "Оплата временно недоступна. Напишите нам в мессенджер, пришлём ссылку."}, origin)
