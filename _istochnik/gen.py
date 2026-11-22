# Собирает многостраничный сайт из index.html (результат build.py): одна разметка, на каждой странице видны свои блоки.
import json, os, re, subprocess, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else "/home/user/memoria-site"
src = open("index.html", encoding="utf-8").read()
cat = json.load(open("catalog.json"))

COLLS = [  # slug, имя, картинка, текст
    ("granat", "Гранат", "img/pomegranate.jpg", "Тёплое золото и красные вставки. Гранат — наш символ: простой снаружи и полный внутри, как сердце человека."),
    ("svetila", "Светила", "img/svetila.jpg", "Солнце, луна и звёзды. Украшения о свете, который не гаснет даже ночью."),
    ("nachalo", "Начало", "img/nachalo.jpg", "Базовые цепочки для каждого дня: то, с чего начинается любой образ."),
    ("cvet-nadezhdy", "Цвет надежды", "img/eyes.jpg", "Бусы из натуральных камней. Цвет, который напоминает: всё будет хорошо."),
    ("nikogda-ne-pozdno", "Никогда не поздно", "img/nikogda.jpg", "Маленькие напоминания о главном: начать сначала никогда не поздно."),
]

def thumb(pred):
    for i in cat:
        if pred(i) and i.get("hit"):
            return i.get("th") or i["photos"][0]
    for i in cat:
        if pred(i):
            return i.get("th") or i["photos"][0]
cats = [("Новинки", "/katalog/?t=new", thumb(lambda i: i.get("new"))),
        ("Колье", "/katalog/?t=neck", thumb(lambda i: i["t"] == "neck")),
        ("Серьги", "/katalog/?t=ear", thumb(lambda i: i["t"] == "ear")),
        ("Кольца", "/katalog/?t=ring", thumb(lambda i: i["t"] == "ring")),
        ("Браслеты", "/katalog/?t=br", thumb(lambda i: i["t"] == "br")),
        ("Сертификаты", "/sertifikaty/", "img/sertifikat.jpg")]
CATS = "".join('<a href="%s"><img src="%s" alt="" loading="lazy">%s</a>' % (h, im, t) for t, h, im in cats)

TITLE = "MEMORIA — вдохновлена красотой рая"
PAGES = [  # путь, страница, заголовок каталога, title
    ("", "home", "Хиты и новинки", TITLE),
    ("katalog/", "katalog", "Все украшения", "Каталог украшений — MEMORIA"),
    ("kollekcii/", "kollekcii", "", "Коллекции — MEMORIA"),
    ("sertifikaty/", "sertifikaty", "", "Подарочные сертификаты — MEMORIA"),
    ("o-brende/", "o-brende", "", "О бренде — MEMORIA"),
    ("dostavka/", "dostavka", "", "Доставка и гарантия — MEMORIA"),
    ("proba-voprosy/", "voprosy", "", "Вопросы и ответы — MEMORIA"),
] + [("kollekcii/%s/" % sl, "coll", "Украшения коллекции", "Коллекция «%s» — MEMORIA" % nm) for sl, nm, _, _ in COLLS]

def page(path, pg, cath, title, coll=None):
    s = src.replace("__PAGE__", pg).replace("__PCOLL__", coll[1] if coll else "").replace("__CATH__", cath)
    s = s.replace("__CATS__", CATS)
    s = s.replace('href="#catalog"', 'href="/%s#catalog"' % path)
    s = s.replace("__CIMG__", coll[2] if coll else "").replace("__CNAME__", coll[1] if coll else "").replace("__CTXT__", coll[3] if coll else "")
    s = s.replace("<title>%s</title>" % TITLE, "<title>%s</title>" % title, 1)
    def hide(m):
        on = m.group(1).split()
        return m.group(0) if pg in on else m.group(0) + " hidden"
    s = re.sub(r'data-on="([^"]*)"', hide, s)
    if pg == "coll":
        s = s.replace('id="cchips"', 'id="cchips" hidden', 1)
    if pg == "home":
        s = s.replace('<div class="filters">', '<div class="filters" hidden>', 1).replace('<p class="count" id="count">', '<p class="count" id="count" hidden>', 1)
    assert "__" not in re.sub(r"__proto__", "", s.split("<script")[0][-2000:])
    tmp = "_page.html"
    open(tmp, "w", encoding="utf-8").write(s)
    os.makedirs(os.path.join(ROOT, path), exist_ok=True)
    subprocess.run([sys.executable, "wrap.py", tmp, os.path.join(ROOT, path, "index.html")], check=True)
    if path.startswith("proba-"):
        f = os.path.join(ROOT, path, "index.html"); h = open(f, encoding="utf-8").read()
        open(f, "w", encoding="utf-8").write(h.replace("<head>", '<head><meta name="robots" content="noindex">', 1))

for path, pg, cath, title in PAGES:
    coll = None
    if pg == "coll":
        coll = next(c for c in COLLS if "kollekcii/%s/" % c[0] == path)
    page(path, pg, cath, title, coll)
print("ok", len(PAGES))
