"""Точная минимизация затрат по ограниченному числу поставщиков.
Учитывает фиксированную доставку и минимальные партии. Без неподтверждённых товаров по умолчанию.
"""
from itertools import combinations
from math import inf


def optimize_split(offers, quantity: int, include_unconfirmed=False, max_days=None):
    qty=int(quantity)
    if qty<=0: raise ValueError('Количество должно быть больше нуля')
    valid=[]
    for row in offers:
        try:
            price=float(row.get('unit_price_kzt') or 0)
            stock=int(row.get('stock') or 0)
            min_qty=max(1,int(row.get('min_qty') or 1))
            shipping=float(row.get('shipping_kzt') or 0)
            days=int(row.get('delivery_days') or 0)
        except (ValueError, TypeError): continue
        if not (price>0 and stock>=min_qty and shipping>=0): continue
        if str(row.get('match_status')) == 'Не подходит':continue
        if not include_unconfirmed and not bool(row.get('confirmed',False)):continue
        if max_days is not None and days>max_days:continue
        valid.append(dict(row,unit_price_kzt=price,stock=stock,min_qty=min_qty,shipping_kzt=shipping,delivery_days=days))
    if len(valid)>14:
        raise ValueError('Допустимо до 14 поставщиков в одном расчёте; сократите список.')
    if sum(x['stock'] for x in valid)<qty:
        return None
    best=None; bestcost=inf
    n=len(valid)
    for size in range(1,n+1):
        for indices in combinations(range(n),size):
            sub=[valid[i] for i in indices]
            min_total=sum(x['min_qty'] for x in sub)
            if min_total>qty or sum(x['stock'] for x in sub)<qty:continue
            alloc={i:valid[i]['min_qty'] for i in indices}
            remaining=qty-min_total
            for i in sorted(indices,key=lambda x: valid[x]['unit_price_kzt']):
                room=valid[i]['stock']-alloc[i]
                take=min(room, remaining)
                alloc[i]+=take;remaining-=take
                if remaining<=0:break
            if remaining: continue
            cost=sum(valid[i]['unit_price_kzt']*alloc[i]+valid[i]['shipping_kzt'] for i in indices)
            if cost<bestcost:
                bestcost=cost
                best={'total_kzt':round(cost,2),'material_kzt':round(sum(valid[i]['unit_price_kzt']*alloc[i] for i in indices),2),
                      'shipping_kzt':round(sum(valid[i]['shipping_kzt'] for i in indices),2),
                      'quantity':qty, 'lines':[
                         {'seller':str(valid[i].get('seller','')), 'quantity':alloc[i],
                          'unit_price_kzt':valid[i]['unit_price_kzt'],
                          'shipping_kzt':valid[i]['shipping_kzt'],
                          'total_kzt':round(valid[i]['unit_price_kzt']*alloc[i]+valid[i]['shipping_kzt'],2),
                          'url':str(valid[i].get('url','')),
                          'confirmed':bool(valid[i].get('confirmed',False))}
                         for i in indices]}
    return best
