"""Cloud Functions backend for the MEMORIA pickup-point selector."""

import base64
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://api.cdek.ru/v2/"
ORIGINS = {"https://memoria-jewelry.ru", "https://www.memoria-jewelry.ru"}
ROUTES = {
    "offices": "deliverypoints",
    "cities": "location/cities",
    "fittingPoints": "deliverypoints",
}
TOKEN = ("", 0)


def request(path, *, data=None, content_type=None, token=None):
    headers = {"Accept": "application/json", "X-App-Name": "widget_pvz",
               "X-App-Version": "4.0.0"}
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(API + path, data=data, headers=headers), timeout=8) as res:
        return json.load(res)


def access_token():
    global TOKEN
    now = time.monotonic()
    if now < TOKEN[1]:
        return TOKEN[0]
    data = urlencode({
        "grant_type": "client_credentials",
        "client_id": os.environ["CDEK_ACCOUNT"],
        "client_secret": os.environ["CDEK_SECRET"],
    }).encode()
    res = request("oauth/token", data=data,
                  content_type="application/x-www-form-urlencoded")
    TOKEN = (res["access_token"], now + max(0, int(res["expires_in"]) - 60))
    return TOKEN[0]


def handler(event, context):
    headers = {"Content-Type": "application/json; charset=utf-8",
               "X-Service-Version": "4.0.0", "Vary": "Origin"}
    origin = next((v for k, v in (event.get("headers") or {}).items()
                   if k.lower() == "origin"), None)

    def reply(status, data=None):
        return {"statusCode": status, "headers": headers,
                "body": json.dumps(data, ensure_ascii=False) if data is not None else ""}

    if origin and origin not in ORIGINS:
        return reply(403, {"message": "Недопустимый источник запроса"})
    if origin:
        headers.update({"Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type",
                        "Access-Control-Expose-Headers": "X-Service-Version"})
    method = event.get("httpMethod", "GET")
    if method == "OPTIONS":
        return reply(204)
    if method not in {"GET", "POST"}:
        return reply(405, {"message": "Метод не поддерживается"})

    try:
        raw = event.get("body") or "{}"
        if len(raw) > 24_000:
            return reply(413, {"message": "Запрос слишком большой"})
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw, validate=True)
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
        params = {**(event.get("queryStringParameters") or {}), **body}
        action = params.pop("action", None)
        path = ROUTES.get(action)
        if not path:
            raise ValueError()
        if action == "cities":
            city = params.get("city", "").strip()
            if not 2 <= len(city) <= 100:
                raise ValueError()
            params = {"city": city, "country_codes": "RU", "size": 30}
        if action in {"offices", "fittingPoints"}:
            city_code = str(params.get("city_code", ""))
            if not re.fullmatch(r"[0-9]{1,10}", city_code):
                raise ValueError()
            params = {"city_code": city_code, "type": "PVZ",
                      "is_dressing_room": "true", "allowed_cod": "true"}
    except (ValueError, TypeError, AttributeError):
        return reply(400, {"message": "Некорректный запрос виджета СДЭК"})

    stage = "authorization"
    try:
        token = access_token()
        stage = path
        result = request(path + "?" + urlencode(params), token=token)
        return reply(200, result)
    except HTTPError as exc:
        print("CDEK upstream status", exc.code)
        return reply(502, {"message": "СДЭК не смог обработать запрос",
                           "stage": stage, "cdekStatus": exc.code})
    except (URLError, TimeoutError, ValueError, TypeError, KeyError) as exc:
        print("CDEK request failed", type(exc).__name__)
        return reply(502, {"message": "Связь со СДЭК временно недоступна"})
