import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import storage

class StorageTests(unittest.TestCase):
    def test_roundtrip_copy_update_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(storage,'DB_PATH',Path(tmp)/'projects.sqlite3'):
                p=storage.save_project({'id':'one','name':'Test tender','category':'IT и электроника','status':'В анализе','mode':'Демо','tender':{'budget_kzt':1000,'items':[{'name':'Ноутбук'}]},'offers':{'0':[{'seller':'A','confirmed':False}]},'hits':{},'optimization':{},'cash':None})
                self.assertEqual(len(storage.get_projects()),1)
                self.assertEqual(storage.get_project('one')['tender']['budget_kzt'],1000)
                p['status']='Готов к решению'
                storage.save_project(p)
                self.assertEqual(storage.get_project('one')['status'],'Готов к решению')
                self.assertEqual(storage.get_project('one')['created_at'],p['created_at'])
                storage.delete_project('one')
                self.assertEqual(storage.get_projects(),[])

if __name__=='__main__':unittest.main()
