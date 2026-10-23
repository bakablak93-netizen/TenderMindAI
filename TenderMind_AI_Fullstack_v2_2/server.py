"""Local, single-user FastAPI backend for TenderMind AI HTML workspace.

Reuses the 0.5 Python engines and the SAME SQLite project schema.
Binds to 127.0.0.1 only via run.py; do not expose on public interfaces.
"""
import csv
import io
import os
from pathlib import Path
from threading import RLock
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import storage
from core.ai import extract_tender, rate_supplier_pages, request_json
from core.finance import cash_guard
from core.optimizer import optimize_split

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
app = FastAPI(title='TenderMind AI Local API', docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=ROOT/'web'), name='static')
lock = RLock()
SESSION = {'OpenAI':'', 'Gemini':''}  # RAM only; never saved or returned
MAX_PROJECTS=1000

class Payload(BaseModel):
    projects: list[dict[str, Any]] = Field(max_length=MAX_PROJECTS)

class AiPayload(BaseModel):
    text: str = Field(min_length=1, max_length=55000)
    provider: str = 'OpenAI'
    model: str = ''

class MatchPayload(BaseModel):
    item: dict[str, Any]
    hits: list[dict[str, Any]] = Field(max_length=24)
    provider: str = 'OpenAI'
    model: str = ''

class SearchPayload(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    specs: str = Field(default='', max_length=500)
    region: str = 'kz-ru'

class OptimizePayload(BaseModel):
    offers: list[dict[str, Any]] = Field(max_length=60)
    quantity: int = Field(gt=0, le=1000000)
    include_unconfirmed: bool = False
    max_days: int | None = Field(default=None, ge=0, le=730)

class CashPayload(BaseModel):
    bid: float = Field(ge=0)
    purchase: float = Field(ge=0)
    delivery: float = Field(ge=0)
    other: float = Field(ge=0)
    starting_cash: float = Field(ge=0)
    customer_advance: float = Field(ge=0)
    purchase_day: int = Field(ge=0, le=730)
    customer_payment_day: int = Field(ge=0, le=730)
    annual_interest_pct: float = Field(default=20, ge=0, le=100)

class SettingsPayload(BaseModel):
    provider: str = 'OpenAI'
    key: str = Field(default='', max_length=500)

class CheckPayload(BaseModel):
    provider: str = 'OpenAI'
    model: str = ''

@app.middleware('http')
async def local_only(request:Request, call_next):
    # Mitigate cross-origin writes from a malicious website open in the same browser.
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin','')
        host=request.headers.get('host','')
        if origin and origin not in (f'http://{host}',f'https://{host}'):
            return JSONResponse({'detail':'Посторонний источник запрещён'},status_code=403)
        if request.headers.get('X-TenderMind-Request')!='local':
            return JSONResponse({'detail':'Требуется заголовок локального приложения'},status_code=403)
    return await call_next(request)

@app.exception_handler(ValueError)
async def invalid_value(request:Request,exc:ValueError):
    return JSONResponse(status_code=400, content={'detail':str(exc)[:400]})

@app.get('/')
def home():
    return FileResponse(ROOT/'web'/'index.html')

@app.get('/styles.css')
def css(): return FileResponse(ROOT/'web'/'styles.css')

@app.get('/app.js')
def frontend(): return FileResponse(ROOT/'web'/'app.js')

@app.get('/integration.js')
def integration(): return FileResponse(ROOT/'web'/'integration.js')

def selected_credential(provider,model):
    if provider not in ('OpenAI','Gemini'):raise ValueError('Неизвестный AI-провайдер')
    key=SESSION[provider] or os.getenv('OPENAI_API_KEY' if provider=='OpenAI' else 'GEMINI_API_KEY','')
    if not key:raise ValueError('Добавьте API-ключ в настройках. Без него доступны демоданные и ручной ввод.')
    model=model.strip() or os.getenv('OPENAI_MODEL' if provider=='OpenAI' else 'GEMINI_MODEL', 'gpt-4.1-mini' if provider=='OpenAI' else 'gemini-2.5-flash')
    return key,model

def clean_number(x, fallback=0):
    try: return float(x or 0)
    except (ValueError,TypeError):return fallback

def core_offer(o):
    return {
        'seller':str(o.get('name',''))[:200], 'unit_price_kzt':clean_number(o.get('price')),
        'stock':int(clean_number(o.get('stock'))), 'min_qty':max(1,int(clean_number(o.get('min_qty'),1) or 1)),
        'shipping_kzt':clean_number(o.get('shipping')), 'delivery_days':int(clean_number(o.get('delivery'))),
        'match_status':str(o.get('match_status','Требует проверки'))[:100],
        'confirmed':bool(o.get('verified',False)), 'url':str(o.get('url',''))[:2000],
        'notes':str(o.get('notes',''))[:700], 'source_id':o.get('source_id'),
    }

def web_offer(o):
    return {
        'name':str(o.get('seller') or o.get('name') or ''), 'price':clean_number(o.get('unit_price_kzt') if 'unit_price_kzt' in o else o.get('price')),
        'stock':o.get('stock',0), 'min_qty':o.get('min_qty',1),
        'shipping':o.get('shipping_kzt',o.get('shipping',0)), 'delivery':o.get('delivery_days',o.get('delivery',0)),
        'verified':str(o.get('confirmed',o.get('verified',False))).lower() in ('true','1','да'), 'url':o.get('url',''),
        'notes':o.get('notes',''), 'source_id':o.get('source_id'), 'match_status':o.get('match_status','Требует проверки')
    }

def to_web(record):
    t=record.get('tender') or {}
    w=t.get('web_ui') or {}
    items=t.get('items') or []
    first=items[0] if items else {}
    offered={str(k):[web_offer(o) for o in v] for k,v in (record.get('offers') or {}).items() if isinstance(v,list)}
    calc=record.get('cash') or {}
    result={
      'id':record['id'], 'title':record['name'], 'category':record.get('category','Прочее'),
      'status':record.get('status','В анализе'), 'demo':record.get('mode','').startswith('Демо'),
      'budget':t.get('budget_kzt') or 0, 'deadline':w.get('deadline') or t.get('deadline') or '',
      'description':w.get('description') or t.get('summary') or '',
      'qty':first.get('quantity') or 1, 'unit':first.get('unit') or 'шт',
      'item':first.get('name') or '', 'specs':first.get('specs') or '',
      'items':items, 'offers':offered.get('0',[]), 'offersByItem':offered,
      'hitsByItem':record.get('hits') or {}, 'optimizationByItem':record.get('optimization') or {},
      'cashCore':record.get('cash'), 'finance':w.get('finance') or ({'calculated':True,'profit':calc.get('gross_margin_kzt',0),'net':calc.get('profit_before_tax_kzt',0),'gap':calc.get('funding_gap_kzt',0)} if calc else None),
      'documentText':w.get('documentText',''), 'aiSummary':t.get('summary',''),
      'warnings':t.get('warnings') or [], 'paymentTerms':t.get('payment_terms') or '',
      'deliveryTerms':t.get('delivery_terms') or '',
      'activeItem':int(w.get('activeItem',0) or 0), 'mode':record.get('mode',''),
    }
    return result

def to_core(p, previous=None):
    prev=previous or {}
    t=dict(prev.get('tender') or {})
    first={'name':str(p.get('item') or ''),'quantity':max(1,int(clean_number(p.get('qty'),1) or 1)),
           'unit':str(p.get('unit') or 'шт'),'specs':str(p.get('specs') or ''),'source_quote':''}
    items=p.get('items')
    if not isinstance(items,list) or not items:
        items=[first] if first['name'] else []
    else:
        items=[{'name':str(i.get('name',''))[:300], 'quantity':max(1,int(clean_number(i.get('quantity'),1) or 1)),
                'unit':str(i.get('unit') or 'шт')[:30], 'specs':str(i.get('specs',''))[:3000],
                'source_quote':str(i.get('source_quote',''))[:1000]} for i in items if isinstance(i,dict) and i.get('name')][:30]
    t.update({'title':str(p.get('title',''))[:300], 'budget_kzt':clean_number(p.get('budget')),
              'items':items,'deadline':str(p.get('deadline') or '')[:30],
              'summary':str(p.get('aiSummary') or p.get('description') or '')[:3000],
              'warnings':p.get('warnings') if isinstance(p.get('warnings'),list) else [],
              'payment_terms':str(p.get('paymentTerms') or '')[:1500],
              'delivery_terms':str(p.get('deliveryTerms') or '')[:1500]})
    t['web_ui']={'description':str(p.get('description') or '')[:5000],
                 'documentText':str(p.get('documentText') or '')[:55000],
                 'deadline':str(p.get('deadline') or '')[:30],
                 'activeItem':int(p.get('activeItem') or 0),
                 'finance':p.get('finance')}
    offers=p.get('offersByItem') if isinstance(p.get('offersByItem'),dict) else {}
    offers=dict(offers)
    if '0' not in offers:offers['0']=p.get('offers') or []
    offers={str(k):[core_offer(o) for o in v[:25] if isinstance(o,dict)] for k,v in offers.items() if isinstance(v,list)}
    return {'id':str(p['id'])[:100], 'name':str(p.get('title') or 'Без названия')[:300],
            'category':str(p.get('category') or 'Прочее')[:100],
            'status':str(p.get('status') or 'В анализе')[:100],
            'mode':'Демо (условные данные)' if p.get('demo') else 'AI-анализ / ручной ввод',
            'created_at':prev.get('created_at') or storage.utcnow(),
            'tender':t, 'offers':offers, 'hits':p.get('hitsByItem') or {},
            'optimization':p.get('optimizationByItem') or {}, 'cash':p.get('cashCore')}

@app.get('/api/bootstrap')
def bootstrap():
    with lock:
        storage.seed_demo_projects()
        return {'projects':[to_web(p) for p in storage.get_projects()], 'provider':'OpenAI', 'status':'SQLite, локальный сервер'}

@app.post('/api/projects/sync')
def sync_projects(payload:Payload):
    with lock:
        current={p['id']:p for p in storage.get_projects()}
        ids=set()
        for p in payload.projects:
            if not isinstance(p.get('id'),str) or not p['id'] or p['id'] in ids:raise ValueError('Некорректный или повторный ID проекта')
            ids.add(p['id'])
        # This is an explicit full snapshot from the local, single-user UI.
        for p in payload.projects:
            storage.save_project(to_core(p,current.get(p['id'])))
        for old_id in current.keys()-ids:
            storage.delete_project(old_id)
    return {'ok':True,'count':len(ids)}

@app.post('/api/documents/extract')
async def document_text(file:UploadFile=File(...)):
    if not file.filename:raise ValueError('Имя файла не указано')
    if Path(file.filename).suffix.lower() not in ('.pdf','.docx','.xlsx','.csv','.txt'):
        raise ValueError('Допускаются PDF, DOCX, XLSX, CSV и TXT')
    payload=await file.read(15*1024*1024+1)
    from core.documents import extract_text
    return {'text':extract_text(file.filename,payload),'filename':Path(file.filename).name}

@app.post('/api/ai/extract')
def analyze(payload:AiPayload):
    key,model=selected_credential(payload.provider,payload.model)
    return {'result':extract_tender(payload.provider,key,model,payload.text),'model':model}

@app.post('/api/ai/match')
def match(payload:MatchPayload):
    key,model=selected_credential(payload.provider,payload.model)
    return {'ratings':rate_supplier_pages(payload.provider,key,model,payload.item,payload.hits),'model':model}

@app.post('/api/ai/check')
def check_ai(payload:CheckPayload):
    key,model=selected_credential(payload.provider,payload.model)
    value=request_json(payload.provider,key,model,'Верни JSON объект {"ok":true}.','Тест подключения')
    return {'ok':value.get('ok') is True,'model':model}

@app.post('/api/settings/key')
def set_key(payload:SettingsPayload):
    if payload.provider not in SESSION:raise ValueError('Неизвестный провайдер')
    SESSION[payload.provider]=payload.key.strip()
    return {'ok':True,'configured':bool(SESSION[payload.provider] or os.getenv('OPENAI_API_KEY' if payload.provider=='OpenAI' else 'GEMINI_API_KEY',''))}

@app.get('/api/settings/status')
def settings_status():
    return {'configured':{p:bool(SESSION[p] or os.getenv('OPENAI_API_KEY' if p=='OpenAI' else 'GEMINI_API_KEY','')) for p in SESSION},
            'models':{'OpenAI':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'Gemini':os.getenv('GEMINI_MODEL','gemini-2.5-flash')}}

@app.post('/api/search')
def find_suppliers(payload:SearchPayload):
    if payload.region not in ('ru-ru','kz-ru','us-en'):raise ValueError('Неизвестный регион')
    from core.search import supplier_search
    hits,errors=supplier_search(payload.name,payload.specs,payload.region)
    return {'hits':hits,'errors':errors}

@app.get('/api/demo-offers')
def example_offers():
    with open(ROOT/'data'/'demo_offers.csv',encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    return {'offers':[web_offer(row) for row in rows],'demo':True}

@app.post('/api/optimize')
def splitbuy(payload:OptimizePayload):
    return {'result':optimize_split([core_offer(o) for o in payload.offers],payload.quantity,payload.include_unconfirmed,payload.max_days)}

@app.post('/api/cash')
def cashguard(payload:CashPayload):
    return {'result':cash_guard(**payload.model_dump())}

@app.get('/api/health')
def health(): return {'ok':True}

@app.post('/api/demo/restore')
def restore_demo():
    with lock:
        count=storage.seed_demo_projects(force=True)
        return {'added':count,'projects':[to_web(p) for p in storage.get_projects()]}

@app.post('/api/demo/reset')
def reset_demo():
    with lock:
        for project in storage.get_projects():storage.delete_project(project['id'])
        storage.seed_demo_projects(force=True)
        return {'projects':[to_web(p) for p in storage.get_projects()]}
