import json,os,sys
from PIL import Image
sys.path.insert(0,'/tmp/claude-0/gen'); from newdesc import D
U='/mnt/user-data/uploads/MEMORIA/'
old={x['sku']:x for x in json.load(open('catalog.json'))}
rows=json.load(open('/tmp/claude-0/gen/rows.json'))
DET={'062':'4,6 г; длина 45+5 см','063':'7,5 г; длина 45+5 см','065':'3,8 г; длина 40+5 см','066':'6,5 г; длина 45+5 см','068':'6,1 г; длина 42+5 см','069':'4,8 г; длина 45+5 см','070':'5 г; длина 40+5 см','071':'5,7 г; длина 47+5 см','072':'5,1 г; длина 47+5 см','073':'10,3 г; длина 42+5 см','074':'5,2 г; длина 40+5 см','079':'7,3 г; длина 40+5 см','076':'3,6 г; длина 17/18+3 см','077':'4,2 г; длина 17,5 см','080':'5,5 г; открытое','081':'10,8 г; Ø 17,3 мм','082':'11,5 г; размеры 6, 7, 8, 9','083':'2,8 г; открытое','084':'10,1 г; длина 16+5,5 см','085':'15,6 г; Ø 6,1 см','086':'31,9 г; Ø 5,8 см','087':'15,1 г; открытый','088':'17,3 г; Ø 6 см, регулируемый','089':'10,1 г; длина 6,9 см','090':'5,1 г; длина 5 см','092':'6,2 г; длина 45+5 см','093':'2,4 г; длина 39,5+5,5 см','108':'длина 40+5 см','109':'длина 45 см','110':'длина 46+5 см','144':'длина 56+5 см','147':'длина 40+5 см','148':'Ø 13 см','151':'длина 50+5 см','094':'длина 17,5 см','113':'длина 18,5+3 см','120':'длина 19,5 см','128':'длина 17,5 см','129':'длина 16,5+5 см','130':'длина 16,5+5 см','131':'длина 16+5 см','138':'длина 20 см'}
quotes={'Исток':('Ибо у Тебя источник жизни; во свете Твоём мы видим свет','Псалом 35:10'),'Живая вода':('И показал мне чистую реку воды жизни, светлую, как кристалл','Откровение 22:1')}
hits={'016','055','061','009','027','034','029','041','046'}
cat={'Украшения на шею':'neck','Серьги':'ear','Браслет':'br','Кольцо':'ring','кольцо':'ring'}
metal={'Золото':'золотистое покрытие','Серебро':'серебристая полированная сталь','Микс':'золотистое и серебристое'}
os.makedirs('img/p/t',exist_ok=True)
for f in os.listdir('img/p'):
  if f.endswith('.jpg'): os.remove('img/p/'+f)
for f in os.listdir('img/p/t'): os.remove('img/p/t/'+f)
items=[]
for r in rows:
  sku=r[0].strip(); m=sku[4:]
  if m in ('150','028','037','044','151'): continue  # решения Эллы
  src=[(U+'посты 4х5/'+sku+'.jpg','1'),(U+'Фото с размерами/'+sku+'.jpg','r')]
  src=[s for s in src if os.path.exists(s[0])]
  if not src: print('nophoto',sku); continue
  photos=[]
  for p,suf in src:
    im=Image.open(p).convert('RGB'); im.thumbnail((1200,1350)); fn=f'img/p/{sku.lower()}-{suf}.jpg'; im.save(fn,quality=80,optimize=True,progressive=True); photos.append(fn)
  im=Image.open(src[0][0]).convert('RGB'); im.thumbnail((560,700)); th=f'img/p/t/{sku.lower()}-{src[0][1]}.jpg'; im.save(th,quality=78,optimize=True,progressive=True)
  r=r+['']*14; c=r[1].strip(); price=int(float(r[7].replace('\xa0','').replace(' ','').replace(',','.'))); met=r[10]; nm=r[11].strip(); coll=r[12].replace('Коллекция','').strip()
  o=old.get(sku)
  desc=o['name'] if o else D.get(m)
  if not desc: print('nodesc',sku); continue
  it=dict(sku=sku,nm=nm,name=desc,price=price,t=cat[c],c=coll,metal=metal.get(met,''),det=(o['det'] if o else DET.get(m,'')),photos=photos,th=th,hit=m in hits,new=int(m[:3])>=62)
  if nm in quotes: it['q']=quotes[nm]
  items.append(it)
order={'neck':0,'ear':1,'ring':2,'br':3}
items.sort(key=lambda x:(not x['hit'],x['photos'][0].endswith('-r.jpg'),order[x['t']],x['sku']))
json.dump(items,open('catalog.json','w'),ensure_ascii=False)
print(len(items), sum(len(i['photos'])>1 for i in items), sum(i['new'] for i in items))
