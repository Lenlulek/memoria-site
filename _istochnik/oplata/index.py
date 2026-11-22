# MEMORIA: создание оплаты в Точке (функция Яндекс Облака, Python 3.12, без библиотек)
# Переменные окружения: TOCHKA_JWT (ключ Точки, обязательно), TG_TOKEN и TG_CHAT (бот уведомлений),
#   MAIL_USER и MAIL_PASS (почта Яндекса для писем о заказах, пароль приложения),
#   SHEET_URL (адрес скрипта Google Таблицы для листа «ЗАКАЗЫ», необязательно),
#   CUSTOMER_CODE и MERCHANT_ID (необязательно: если пусто, узнаём сами).
import json, os, re, time, hashlib, smtplib, urllib.request, urllib.error, urllib.parse
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr

API = "https://enter.tochka.com/uapi"
SITE = "https://memoria-jewelry.ru"
ORIGINS = {SITE, "https://www.memoria-jewelry.ru"}
PROMO = {"MEMORIA10": 0.10}          # скидка только на украшения, не на сертификаты
MIN_CERT, MAX_CERT = 1000, 100000
CDEK_DEPOSIT = 500                  # предоплата доставки для «СДЭК с примеркой»
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
        if sku == "CDEK-DEPOSIT":
            # «СДЭК с примеркой»: оплачиваем только предоплату доставки, украшения — при получении
            cart = body.get("cart") or []
            for c in cart[:30]:
                cs = str(c.get("sku", ""))
                if not (prices.get(cs) or re.fullmatch(r"CERT-\d+-[EP]", cs)):
                    raise ValueError("Нет такого украшения: " + cs)
                cq = int(c.get("q", 0))
                skus.append(cs + (" x%d" % cq if cq > 1 else ""))
            if not skus:
                raise ValueError("Корзина пуста")
            return ([{"name": "Предоплата доставки СДЭК (зачитывается при выкупе)", "amount": CDEK_DEPOSIT, "quantity": 1,
                      "paymentMethod": "full_prepayment", "paymentObject": "service", "vatType": "none", "measure": "шт."}],
                    skus, CDEK_DEPOSIT)
        if not 1 <= q <= 20:
            raise ValueError("Неверное количество")
        m = re.fullmatch(r"CERT-(\d+)-([EP])", sku)
        if m:
            n = int(m.group(1))
            if not MIN_CERT <= n <= MAX_CERT:
                raise ValueError("Неверная сумма сертификата")
            items.append({"name": "Подарочный сертификат MEMORIA на %d руб." % n, "amount": n,
                          "quantity": q, "paymentMethod": "full_prepayment", "paymentObject": "goods",
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

SERVICES = {"ozon": "Ozon", "cdek": "СДЭК", "yandex": "Яндекс Доставка", "cdektry": "СДЭК с примеркой"}

def _clean(v, n=200):
    return re.sub(r"[\x00-\x1f<>]", " ", str(v or "")).strip()[:n]

def _lines(v):
    return "\n".join(_clean(x, 300) for x in str(v or "").split("\n") if x.strip())[:2000]

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

def _mail(subject, text, to=None):
    user, pw = os.environ.get("MAIL_USER", "").strip(), os.environ.get("MAIL_PASS", "").strip()
    if not user or not pw:
        return "no mail settings"
    to = to or user
    m = MIMEText(text, "plain", "utf-8")
    m["Subject"], m["To"] = Header(subject, "utf-8"), to
    m["From"] = formataddr((str(Header("MEMORIA", "utf-8")), user))
    with smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=15) as srv:
        srv.login(user, pw)
        srv.sendmail(user, [to], m.as_string())
    return "ok"

def _sheet(payload):
    """Строка в лист «ЗАКАЗЫ» Google Таблицы через скрипт таблицы (без имени, телефона и адреса)."""
    url = os.environ.get("SHEET_URL", "").strip()
    if not url:
        return "no sheet settings"
    r = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as f:
        return f.read().decode(errors="replace")[:200]

def _sheet_items(purpose):
    """Из назначения платежа «Заказ … : MEM-055, MEM-075 x2, сертификат 3000» собираем позиции с ценами сайта."""
    part = purpose.split(": ", 1)[1] if ": " in purpose else ""
    try:
        prices = _prices()
    except Exception:
        prices = {}
    out = []
    for x in [y.strip() for y in part.split(",") if y.strip()]:
        m = re.fullmatch(r"сертификат (\d+)", x)
        if m:
            out.append({"sku": "сертификат", "cert": True, "q": 1, "price": int(m.group(1))})
            continue
        m = re.fullmatch(r"(MEM-\d+)(?: x(\d+))?", x)
        if m:
            out.append({"sku": m.group(1), "q": int(m.group(2) or 1), "price": (prices.get(m.group(1)) or {}).get("price", 0)})
    return out

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
            "Получатель: %s\nТелефон: %s\nПочта: %s\nНовости MEMORIA: %s\nДоставка: %s\nГород: %s\nПункт выдачи: %s\nКомментарий: %s\n\nСостав:\n%s\n") % (
        purpose, amount, op, _clean(d.get("name"), 100), phone, _clean(body.get("email"), 100),
        "да, согласна получать" if body.get("news") is True else "нет",
        SERVICES.get(d.get("service"), "Ozon"), _clean(d.get("city"), 100), _clean(d.get("point"), 300),
        _clean(d.get("comment"), 300), _lines(body.get("lines")))
    res = {"paid": True}
    buyer = _clean(body.get("email"), 100)
    num = re.search(r"Заказ (\S+)", purpose)
    num = num.group(1) if num else ""
    sv = SERVICES.get(d.get("service"), "Ozon")
    dep = purpose.startswith("Предоплата СДЭК")
    if dep:
        num = (re.search(r"Предоплата СДЭК (\S+)", purpose) or [None, ""])[1]
        short = "🛍 Новый заказ: СДЭК с примеркой, предоплата %s руб. внесена!\n%s\nДанные доставки — в письме на почте." % (amount, purpose)
        full = full.replace("Новый оплаченный заказ", "Новый заказ «СДЭК с примеркой» (внесена предоплата доставки %s руб., украшения — оплата при получении)" % amount, 1)
    client = ("Здравствуйте%s!\n\nСпасибо за заказ в MEMORIA 🤍\nЗаказ № %s оплачен и принят в работу.\n\n"
              "Состав:\n%s\n\nСумма: %s руб.\nДоставка: %s, пункт выдачи: %s, %s\n\n"
              "Отправим за 1–3 рабочих дня и пришлём трек-номер. Чек об оплате придёт отдельным письмом от Точка Банка.\n\n"
              "Если есть вопросы, ответьте на это письмо или напишите нам в Telegram, MAX или WhatsApp по номеру +7 926 615-93-09.\n\nMEMORIA\nmemoria-jewelry.ru\n") % (
        (", " + _clean(d.get("name"), 100).split(" ")[0]) if _clean(d.get("name"), 100) else "", num,
        "\n".join(x for x in _lines(body.get("lines")).split("\n") if not x.startswith("Итого")), amount, sv, _clean(d.get("city"), 100), _clean(d.get("point"), 300))
    if dep:
        client = ("Здравствуйте%s!\n\nСпасибо за заказ в MEMORIA 🤍\nЗаказ № %s принят: СДЭК с примеркой.\n\n"
                  "Состав:\n%s\n\nПредоплата доставки: %s руб. Она зачтётся в стоимость украшений, если вы что-то оставите себе. "
                  "Остальное оплатите в пункте СДЭК после примерки, только за то, что понравилось.\n"
                  "Пункт выдачи: %s, %s\n\nОтправим за 1–3 рабочих дня и пришлём трек-номер СДЭК. Чек о предоплате придёт отдельным письмом от Точка Банка.\n\n"
                  "Если есть вопросы, ответьте на это письмо или напишите нам в Telegram, MAX или WhatsApp по номеру +7 926 615-93-09.\n\nMEMORIA\nmemoria-jewelry.ru\n") % (
            (", " + _clean(d.get("name"), 100).split(" ")[0]) if _clean(d.get("name"), 100) else "", num,
            _lines(body.get("lines")), amount, _clean(d.get("city"), 100), _clean(d.get("point"), 300))
    jobs = [("tg", lambda: _tg(short)), ("mail", lambda: _mail(("Новый заказ СДЭК с примеркой, предоплата %s руб." if dep else "Новый заказ с сайта MEMORIA: %s руб.") % amount, full))]
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", buyer):
        jobs.append(("client", lambda: _mail("Ваш заказ № %s в MEMORIA принят" % num, client, buyer)))
    if not dep:
      jobs.append(("sheet", lambda: _sheet({"order": num, "items": _sheet_items(purpose), "promo": " промокод" in purpose,
                                          "service": sv, "amount": amount})))
    for name, fn in jobs:
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
        if action == "testsheet":
            try:
                return _out(200, {"sheet": _sheet({"ping": True})}, origin)
            except Exception as e:
                return _out(200, {"sheet": "error: %s" % e}, origin)
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
        dep = items[0]["name"].startswith("Предоплата доставки СДЭК")
    except ValueError as e:
        return _out(400, {"error": str(e)}, origin)
    except Exception as e:
        print("BAD REQUEST", repr(e))
        return _out(400, {"error": "Не удалось прочитать заказ"}, origin)
    try:
        cc, mid = _ids()
        if promo in PROMO and not dep:
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
                "purpose": ("%s %s с сайта MEMORIA%s PR%s: %s" % ("Предоплата СДЭК" if dep else "Заказ", order, " промокод" if promo in PROMO else "", tag, ", ".join(skus)))[:140],
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
