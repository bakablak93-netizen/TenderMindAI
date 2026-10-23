import unittest
from core.finance import cash_guard
from core.optimizer import optimize_split
from core.ai import parse_json
from core.documents import extract_text

class BasicTests(unittest.TestCase):
    def test_json(self):
        self.assertEqual(parse_json('```json\n{"x":1}\n```')['x'],1)
    def test_docs_txt(self):
        self.assertIn('Тендер',extract_text('a.txt','Тендер'.encode('utf-8')))
    def test_split_cheaper_two_suppliers(self):
        offers=[
            {'seller':'A','unit_price_kzt':260,'stock':100,'min_qty':1,'shipping_kzt':50,'delivery_days':5,'confirmed':True,'match_status':'Возможно подходит'},
            {'seller':'B','unit_price_kzt':240,'stock':60,'min_qty':1,'shipping_kzt':100,'delivery_days':5,'confirmed':True,'match_status':'Возможно подходит'}]
        r=optimize_split(offers,100)
        self.assertEqual(r['material_kzt'],24800)
        self.assertEqual(r['total_kzt'],24950)
        self.assertEqual(sum(line['quantity'] for line in r['lines']),100)
    def test_fixed_shipping_changes_choice(self):
        offers=[
            {'seller':'A','unit_price_kzt':100,'stock':10,'min_qty':1,'shipping_kzt':0,'confirmed':True},
            {'seller':'B','unit_price_kzt':90,'stock':10,'min_qty':1,'shipping_kzt':200,'confirmed':True}]
        self.assertEqual(optimize_split(offers,10)['total_kzt'],1000)
    def test_unconfirmed_excluded(self):
        o=[{'seller':'A','unit_price_kzt':100,'stock':10,'confirmed':False}]
        self.assertIsNone(optimize_split(o,10))
        self.assertIsNotNone(optimize_split(o,10,True))
    def test_cash_gap(self):
        r=cash_guard(3000,2500,0,0,1000,0,0,30,20)
        self.assertEqual(r['funding_gap_kzt'],1500)
        self.assertGreater(r['estimated_interest_kzt'],0)
    def test_cash_no_gap(self):
        r=cash_guard(3000,2500,0,0,3000,0,0,30,20)
        self.assertEqual(r['funding_gap_kzt'],0)
        self.assertEqual(r['estimated_interest_kzt'],0)

if __name__=='__main__': unittest.main()
