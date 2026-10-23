"""Настоящий веб-поиск. Возвращает только URL, которые реально пришли от поискового источника.
Результаты поиска — лиды, а НЕ подтверждённые оферты.
"""
from urllib.parse import urlparse
from ddgs import DDGS


def supplier_search(item_name: str, specs: str, region='ru-ru', max_results=12):
    name = ' '.join((item_name or '').split())[:110]
    specs = ' '.join((specs or '').split())[:100]
    if not name: raise ValueError('Укажите наименование товара')
    searches = [f'{name} {specs} купить оптом Казахстан цена поставщик',
                f'{name} {specs} site:satu.kz OR site:kaspi.kz']
    results=[]; seen=set(); errors=[]
    searcher=DDGS(timeout=14)
    for query in searches:
        try:
            hits = searcher.text(query,region=region,max_results=max(4, max_results//2)) or []
            for hit in hits:
                href=(hit.get('href') or hit.get('url') or '').strip()
                u=urlparse(href)
                if u.scheme not in ('http','https') or not u.netloc or href in seen:
                    continue
                if u.username or u.password or u.hostname in ('localhost','127.0.0.1'):
                    continue
                seen.add(href)
                results.append({'source_id':len(results)+1,'title':str(hit.get('title',''))[:180],
                                'url':href,'snippet':str(hit.get('body',''))[:500]})
                if len(results)>=max_results: break
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {str(exc)[:180]}')
        if len(results)>=max_results: break
    return results, errors
