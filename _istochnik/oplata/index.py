# MEMORIA: создание оплаты в Точке (функция Яндекс Облака, Python 3.12, без библиотек)
# Переменные окружения: TOCHKA_JWT (ключ Точки, обязательно), TG_TOKEN и TG_CHAT (бот уведомлений),
#   MAIL_USER и MAIL_PASS (почта Яндекса для писем о заказах, пароль приложения),
#   CUSTOMER_CODE и MERCHANT_ID (необязательно: если пусто, узнаём сами).
import json, os, re, time, hashlib, smtplib, urllib.request, urllib.error, urllib.parse
from email.mime.text import MIMEText

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
        raise RuntimeError("tochka %s %s: %s" % (e.code, url.replace(API, ""), body[:600]))

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

def _phone_tag(phone):
    """Короткая метка телефона (сам номер в банк не уходит)."""
    d = re.sub(r"\D", "", str(phone))[-10:]
    if len(d) != 10:
        return None
    salt = os.environ.get("PROMO_SALT", "memoria-pom")
    return hashlib.sha256((salt + d).encode()).hexdigest()[:8]

def _promo_used(cc, tag):
    """Был ли уже ОПЛАЧЕННЫЙ заказ с промокодом на этот телефон (по истории Точки за год)."""
    t = time.gmtime()
    q = "customerCode=%s&fromDate=%s&toDate=%s" % (cc, time.strftime("%Y-%m-%d", time.gmtime(time.time() - 365 * 86400)),
                                                  time.strftime("%Y-%m-%d", time.gmtime(time.time() + 86400)))
    ops = _req(API + "/acquiring/v1.0/payments?" + q)["Data"].get("Operation", [])
    for o in ops:
        if ("PR" + tag) in str(o.get("purpose", "")).replace(" ", "") and str(o.get("status", "")).upper() in ("APPROVED", "AUTHORIZED", "PAID"):
            return True
    return False

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
        price = int(price) if price == int(price) else price
        items.append({"name": (it["name"] + " " + sku)[:128], "amount": price, "quantity": q,
                      "paymentMethod": "full_payment", "paymentObject": "goods",
                      "vatType": "none", "measure": "шт."})
        skus.append(sku + (" x%d" % q if q > 1 else ""))
    if not items:
        raise ValueError("Корзина пуста")
    total = round(sum(i["amount"] * i["quantity"] for i in items), 2)
    total = int(total) if total == int(total) else total
    return items, skus, total

SERVICES = {"ozon": "Ozon", "cdek": "СДЭК", "yandex": "Яндекс Доставка"}

def _clean(v, n=200):
    return re.sub(r"[\x00-\x1f<>]", " ", str(v or "")).strip()[:n]

def _delivery(body):
    d = body.get("delivery") or {}
    res = {"name": _clean(d.get("name"), 100), "city": _clean(d.get("city"), 100),
           "service": SERVICES.get(d.get("service"), "Ozon"), "point": _clean(d.get("point"), 300),
           "comment": _clean(d.get("comment"), 300)}
    if not res["name"] or not res["city"] or not res["point"]:
        raise ValueError("Заполните имя, город и адрес пункта выдачи")
    return res

def _tg(text):
    tok, chat = os.environ.get("TG_TOKEN", "").strip(), os.environ.get("TG_CHAT", "").strip()
    if not tok or not chat:
        return "no tg settings"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    with urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % tok, data=data, timeout=10) as f:
        return f.status

def _mail(subject, text):
    user, pw = os.environ.get("MAIL_USER", "").strip(), os.environ.get("MAIL_PASS", "").strip()
    if not user or not pw:
        return "no mail settings"
    m = MIMEText(text, "plain", "utf-8")
    m["Subject"], m["From"], m["To"] = subject, user, user
    with smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=15) as srv:
        srv.login(user, pw)
        srv.sendmail(user, [user], m.as_string())
    return "ok"

def _notify(body):
    """Покупатель вернулся с оплаты: проверяем в Точке, что заказ оплачен, и сообщаем Элле."""
    op = re.sub(r"[^0-9a-fA-F-]", "", str(body.get("operationId", "")))[:64]
    if not op:
        raise ValueError("нет номера операции")
    o = _req(API + "/acquiring/v1.0/payments/" + op)["Data"]
    o = (o.get("Operation") or [o])[0] if isinstance(o, dict) else o
    status = str(o.get("status", "")).upper()
    if status not in ("APPROVED", "AUTHORIZED", "PAID"):
        return {"paid": False, "status": status}
    purpose, amount = o.get("purpose", ""), o.get("amount", "")
    d = body.get("delivery") or {}
    phone = _clean(body.get("phone"), 30)
    short = "🛍 Новый заказ оплачен!\n%s\nСумма: %s руб.\nДанные доставки — в письме на почте." % (purpose, amount)
    full = ("Новый оплаченный заказ с сайта MEMORIA\n\n%s\nСумма: %s руб.\nОперация Точки: %s\n\n"
            "Получатель: %s\nТелефон: %s\nПочта: %s\nДоставка: %s\nГород: %s\nПункт выдачи: %s\nКомментарий: %s\n\nСостав:\n%s\n") % (
        purpose, amount, op, _clean(d.get("name"), 100), phone, _clean(body.get("email"), 100),
        SERVICES.get(d.get("service"), "Ozon"), _clean(d.get("city"), 100), _clean(d.get("point"), 300),
        _clean(d.get("comment"), 300), _clean(body.get("lines"), 2000))
    res = {"paid": True}
    for name, fn in (("tg", lambda: _tg(short)), ("mail", lambda: _mail("Новый заказ с сайта MEMORIA: %s руб." % amount, full))):
        try:
            res[name] = fn()
        except Exception as e:
            print("NOTIFY", name, repr(e)); res[name] = "error: %s" % e
    return res

def _tg_setup():
    tok = os.environ.get("TG_TOKEN", "").strip()
    with urllib.request.urlopen("https://api.telegram.org/bot%s/getUpdates" % tok, timeout=10) as f:
        u = json.loads(f.read().decode())
    chats = {}
    for x in u.get("result", []):
        c = (x.get("message") or {}).get("chat") or {}
        if c.get("id"):
            chats[str(c["id"])] = c.get("first_name") or c.get("title") or ""
    return {"chats": chats}

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
        action = body.get("action", "pay")
        if action == "tgsetup":
            return _out(200, _tg_setup(), origin)
        if action == "notify":
            try:
                return _out(200, _notify(body), origin)
            except Exception as e:
                print("NOTIFY ERROR", repr(e))
                return _out(200, {"paid": None, "error": str(e)[:300]}, origin)
        if action == "testnotify":
            res = {}
            for name, fn in (("tg", lambda: _tg("Проверка: уведомления MEMORIA работают 🤍")),
                             ("mail", lambda: _mail("Проверка уведомлений MEMORIA", "Если вы видите это письмо, письма о заказах будут приходить сюда."))):
                try:
                    res[name] = fn()
                except Exception as e:
                    res[name] = "error: %s" % e
            return _out(200, res, origin)
        email = str(body.get("email", "")).strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 100:
            return _out(400, {"error": "Укажите почту для чека"}, origin)
        promo = str(body.get("promo", "")).strip().upper()
        tag = _phone_tag(body.get("phone", ""))
        if not tag:
            return _out(400, {"error": "Укажите телефон получателя"}, origin)
        if "delivery" in body:
            _delivery(body)
        if promo not in PROMO:
            body["promo"] = ""
        items, skus, total = build_order(body, _prices())
    except ValueError as e:
        return _out(400, {"error": str(e)}, origin)
    except Exception as e:
        print("BAD REQUEST", repr(e))
        return _out(400, {"error": "Не удалось прочитать заказ"}, origin)
    try:
        cc, mid = _ids()
        if promo in PROMO:
            try:
                used = _promo_used(cc, tag)
            except Exception as e2:
                print("PROMO CHECK FAILED", repr(e2))
                used = False
                if h.get("x-debug"):
                    return _out(502, {"error": "promo check", "detail": str(e2)[:900]}, origin)
            if used:
                return _out(400, {"error": "Промокод действует только на первый заказ. Уберите его, и можно оплатить."}, origin)
        order = time.strftime("%d%m-%H%M%S", time.gmtime(time.time() + 3 * 3600))
        data = {"customerCode": cc, "merchantId": mid, "amount": total,
                "purpose": ("Заказ %s с сайта MEMORIA%s PR%s: %s" % (order, " промокод" if promo in PROMO else "", tag, ", ".join(skus)))[:140],
                "paymentMode": ["sbp", "card"],
                "redirectUrl": SITE + "/?oplata=ok&z=" + order,
                "failRedirectUrl": SITE + "/?oplata=fail",
                "Client": {"email": email},
                "Items": items}
        try:
            r = _req(API + "/acquiring/v1.0/payments_with_receipt", {"Data": data})["Data"]
        except RuntimeError as e1:
            if "Payment type" not in str(e1):
                raise
            data["paymentMode"] = ["card"]
            r = _req(API + "/acquiring/v1.0/payments_with_receipt", {"Data": data})["Data"]
        print("ORDER", order, total, r.get("operationId"))
        return _out(200, {"url": r["paymentLink"], "order": order, "total": total, "op": r.get("operationId")}, origin)
    except Exception as e:
        print("PAY ERROR", repr(e))
        res = {"error": "Оплата временно недоступна. Напишите нам в мессенджер, пришлём ссылку."}
        if h.get("x-debug"):
            res = {"detail": str(e)[-500:]}
        return _out(502, res, origin)
