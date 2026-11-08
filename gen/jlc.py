"""JLCPCB parts search helper.

python3 jlc.py <keyword>...   -> top hits with LCSC id, stock, library type
"""
import json, sys, urllib.request

URL = 'https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList'


def search(keyword, n=8):
    body = json.dumps({'keyword': keyword, 'currentPage': 1, 'pageSize': n}).encode()
    req = urllib.request.Request(URL, data=body, headers={'Content-Type': 'application/json',
                                                          'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    return ((d.get('data') or {}).get('componentPageInfo') or {}).get('list') or []


def fmt(c):
    lib = {'base': 'BASIC', 'expand': 'ext'}.get(c.get('componentLibraryType'), c.get('componentLibraryType'))
    if c.get('preferredComponentFlag'):
        lib = 'PREF'
    p = (c.get('componentPrices') or [{}])[0].get('productPrice')
    return '%-10s %-30s %-20s st=%-7s %-5s $%s' % (c.get('componentCode'), (c.get('componentModelEn') or '')[:30],
                                                   (c.get('componentSpecificationEn') or '')[:20],
                                                   c.get('stockCount'), lib, p)


if __name__ == '__main__':
    for q in sys.argv[1:]:
        print('==', q)
        for c in search(q):
            print('  ' + fmt(c))
