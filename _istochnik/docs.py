# Собирает страницы /pokupatelyam/, /oferta/, /privacy/ из текстов в _istochnik/docs/*.txt
# Запуск: python3 docs.py <папка репозитория>
import re, sys, os, html
R = sys.argv[1] if len(sys.argv) > 1 else '..'
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs')
PAGES = [
    ('pokupatelyam', 'Покупателям', 'Оплата, доставка, гарантия, возврат и реквизиты MEMORIA.'),
    ('oferta', 'Публичная оферта', 'Условия дистанционной продажи украшений MEMORIA.'),
    ('privacy', 'Политика обработки персональных данных', 'Как MEMORIA обрабатывает и защищает персональные данные.'),
    ('soglasie', 'Согласие на обработку персональных данных', 'Согласие на обработку персональных данных для программы лояльности MEMORIA.'),
]
CSS = """
:root{--milk:#FBF7F1;--paper:#F3ECE2;--granat:#8C2A2E;--ink:#2B2427;--muted:#7A6E6C;--line:#E4D9CD;color-scheme:light}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{background:var(--milk);color:var(--ink);font:300 16px/1.65 "Commissioner","Segoe UI",Arial,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line)}
header .wrap{display:flex;justify-content:space-between;align-items:center;padding-block:18px;gap:16px}
.logo{font:500 22px/1 "Cormorant Garamond",serif;letter-spacing:.32em;color:var(--granat);text-decoration:none}
.back{font-size:14px;color:var(--muted);text-decoration:none}
h1{font:500 clamp(30px,6vw,44px)/1.1 "Cormorant Garamond",serif;margin:48px 0 8px}
h2{font:500 24px/1.25 "Cormorant Garamond",serif;color:var(--granat);margin:36px 0 8px}
p,li{margin:0 0 10px;overflow-wrap:anywhere}
.lead{color:var(--muted);margin-bottom:28px}
ul{padding-left:20px}
a{color:var(--granat)}
nav.docs{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:14px;margin-top:8px}
footer{margin-top:72px;background:var(--paper);border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
footer .wrap{padding-block:28px}
"""
def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
    s = re.sub(r'(?<!["=>])(https?://[^\s<,;)]+)', lambda m: '<a href="%s">%s</a>' % (m.group(1).rstrip('.'), m.group(1).rstrip('.')) + ('.' if m.group(1).endswith('.') else ''), s)
    s = re.sub(r'([\w.]+@[\w.]+\.ru)', r'<a href="mailto:\1">\1</a>', s)
    s = s.replace('в публичной оферте', 'в <a href="/oferta/">публичной оферте</a>')
    return s
def body(lines):
    out, ul = [], False
    for i, l in enumerate(lines):
        li = l.startswith('- ') or l.startswith('• ')
        if ul and not li: out.append('</ul>'); ul = False
        if l.startswith('## '):
            ids = {'Оплата': 'oplata', 'Доставка': 'dostavka', 'Гарантия': 'garantiya', 'Возврат': 'vozvrat', 'Продавец': 'rekvizity'}
            out.append('<h2%s>%s</h2>' % ((' id="%s"' % ids[l[3:]]) if l[3:] in ids else '', inline(l[3:])))
        elif re.match(r'^\d+\.\s', l): out.append('<h2>%s</h2>' % inline(l))
        elif li:
            if not ul: out.append('<ul>'); ul = True
            out.append('<li>%s</li>' % inline(l[2:]))
        elif i < 2 and (l.startswith('Редакция') or l.startswith('Условия')): out.append('<p class="lead">%s</p>' % inline(l))
        else: out.append('<p>%s</p>' % inline(l))
    if ul: out.append('</ul>')
    return '\n'.join(out)
nav = ''.join('<a href="/%s/">%s</a>' % (s, t) for s, t, _ in PAGES)
for slug, title, desc in PAGES:
    lines = [l.strip() for l in open(os.path.join(D, slug + '.txt'), encoding='utf-8') if l.strip()]
    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — MEMORIA</title><meta name="description" content="{desc}">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500&family=Commissioner:wght@300;400&display=swap">
<style>{CSS}</style></head><body>
<header><div class="wrap"><a class="logo" href="/">MEMORIA</a><a class="back" href="/">← Вернуться к украшениям</a></div></header>
<main class="wrap"><h1>{title}</h1>
{body(lines)}
</main>
<footer><div class="wrap">© MEMORIA, 2026 · ИП Курбатова Элла, ИНН 771371492235<nav class="docs">{nav}</nav></div></footer>
</body></html>
"""
    os.makedirs(os.path.join(R, slug), exist_ok=True)
    open(os.path.join(R, slug, 'index.html'), 'w', encoding='utf-8').write(page)
    print(slug, len(page))
