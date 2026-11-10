import json
s=open('tpl.html').read().replace('__OUV__',open('ouv.b64').read())
o=json.load(open('orn.json'))
for k,v in o.items(): s=s.replace(f'__{k}__',v)
s=s.replace('__CATALOG__',open('catalog.json').read())
open('index.html','w').write(s); assert '__' not in s.replace('__proto__','')[:0]+''
print(len(s), [k for k in ['__POM__','__SEEDS'] if k in s])
