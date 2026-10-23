import io
from fastapi.testclient import TestClient
import pytest
from core import storage
from server import app, to_web, to_core

HEAD={'X-TenderMind-Request':'local'}

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage,'DB_PATH',tmp_path/'app.sqlite3')
    with TestClient(app) as c: yield c

def test_bootstrap_6_demos(client):
    r=client.get('/api/bootstrap');assert r.status_code==200
    ps=r.json()['projects'];assert len(ps)==6
    assert len({p['category'] for p in ps})==6
    assert all(p['demo'] for p in ps)
    assert len(client.get('/api/bootstrap').json()['projects'])==6

def test_save_retrieve_multi_items_original_schema(client):
    p=client.get('/api/bootstrap').json()['projects'][0]
    p['title']='Проверка интеграции'
    p['demo']=False
    p['items']=[{'name':'Товар А','quantity':3,'unit':'шт','specs':'Требования','source_quote':'Из PDF'}, {'name':'Товар Б','quantity':2,'unit':'шт','specs':'Спецификация','source_quote':'Из ТЗ'}]
    p['offersByItem']={'0':[{'name':'A','price':120,'stock':5,'min_qty':1,'shipping':10,'delivery':5,'verified':True,'match_status':'Возможно подходит'}],'1':[]}
    p['offers']=p['offersByItem']['0']
    p['documentText']='Полный документ';p['cashCore']={'funding_gap_kzt':99,'profit_before_tax_kzt':8}
    other=client.get('/api/bootstrap').json()['projects'][1:]
    res=client.post('/api/projects/sync',json={'projects':[p]+other},headers=HEAD);assert res.status_code==200,res.text
    updated=client.get('/api/bootstrap').json()['projects']
    check=next(x for x in updated if x['id']==p['id'])
    assert check['items'][1]['name']=='Товар Б'
    assert check['offersByItem']['0'][0]['verified'] is True
    assert check['documentText']=='Полный документ'
    assert check['cashCore']['funding_gap_kzt']==99
    original=storage.get_project(p['id'])
    assert original['tender']['items'][1]['quantity']==2
    assert original['offers']['0'][0]['seller']=='A'
    assert original['tender']['items'][0]['source_quote']=='Из PDF'

def test_optimizer_and_cash_guard(client):
    data={'offers':[{'name':'Доставка A','price':100,'stock':7,'min_qty':2,'shipping':5,'delivery':4,'verified':True},
                    {'name':'Доставка B','price':80,'stock':5,'min_qty':1,'shipping':10,'delivery':6,'verified':True}],
          'quantity':8,'include_unconfirmed':False}
    res=client.post('/api/optimize',json=data,headers=HEAD)
    assert res.status_code==200,res.text
    val=res.json()['result'];assert val['quantity']==8
    assert sum(x['quantity'] for x in val['lines'])==8
    assert val['total_kzt']>val['material_kzt']
    res=client.post('/api/cash',json={'bid':2000,'purchase':1300,'delivery':100,'other':100,'starting_cash':0,'customer_advance':0,'purchase_day':0,'customer_payment_day':45,'annual_interest_pct':20},headers=HEAD)
    assert res.status_code==200,res.text
    val=res.json()['result']
    assert val['funding_gap_kzt']==1500
    assert val['first_gap_day']==0
    assert val['profit_before_tax_kzt']<500
    assert len(val['timeline'])>=2

def test_documents_file_and_invalid_origin(client):
    r=client.post('/api/documents/extract',headers=HEAD,files={'file':('tender.txt',b'hello document','text/plain')})
    assert r.status_code==200;rtext=r.json()['text'];assert rtext=='hello document'
    bad=client.post('/api/documents/extract',headers={**HEAD,'Origin':'https://example.com'},files={'file':('tender.txt',b'hello document','text/plain')})
    assert bad.status_code==403
    untrusted=client.post('/api/projects/sync',json={'projects':[]})
    assert untrusted.status_code==403
    oversized=client.post('/api/documents/extract',headers=HEAD,files={'file':('tender.txt',b'a'*(15*1024*1024+1))})
    assert oversized.status_code==400

def test_settings_not_echo_key_and_ai_requires_key(client):
    client.get('/api/bootstrap')
    resp=client.post('/api/settings/key',json={'provider':'OpenAI','key':'temporary-secret'},headers=HEAD)
    assert resp.status_code==200
    assert 'temporary-secret' not in resp.text
    assert 'temporary-secret' not in client.get('/api/settings/status').text
    from server import SESSION
    SESSION['OpenAI']=''
    resp=client.post('/api/ai/extract',headers=HEAD,json={'text':'Тест документа','provider':'OpenAI'})
    assert resp.status_code==400

def test_demo_restore_and_reset(client):
    ps=client.get('/api/bootstrap').json()['projects']
    resp=client.post('/api/projects/sync',json={'projects':ps[:5]},headers=HEAD)
    assert resp.status_code==200
    r=client.post('/api/demo/restore',json={},headers=HEAD)
    assert r.status_code==200
    assert len(r.json()['projects'])==6
    r=client.post('/api/demo/reset',json={},headers=HEAD)
    assert r.status_code==200
    assert len(r.json()['projects'])==6
