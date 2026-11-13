# собирает index.html для GitHub Pages из фрагмента build.py
import sys
src,dst=sys.argv[1],sys.argv[2]
s=open(src,encoding='utf-8').read().replace('<meta name="claude:viewport-fit-sides" content="cover">\n','')
head='''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>html,body{margin:0;padding:0}</style>
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="MEMORIA">
<meta property="og:title" content="MEMORIA — вдохновлена красотой рая">
<meta property="og:description" content="Колье, серьги, кольца и браслеты. Не боятся воды, гипоаллергенно. Заказ в Telegram, WhatsApp и MAX.">
<meta property="og:url" content="https://memoria-jewelry.ru/">
<meta property="og:image" content="https://memoria-jewelry.ru/img/og.jpg">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
'''
j=s.find('\n',s.find('</style>'))+1
open(dst,'w',encoding='utf-8').write(head+s[:j]+'</head>\n<body>\n'+s[j:]+'\n</body>\n</html>\n')
