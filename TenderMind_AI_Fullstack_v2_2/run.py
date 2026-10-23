"""Start TenderMind AI on localhost and open the default browser."""
import threading
import webbrowser

import uvicorn

if __name__=='__main__':
    threading.Timer(2,lambda: webbrowser.open('http://127.0.0.1:8501')).start()
    uvicorn.run('server:app',host='127.0.0.1',port=8501,reload=False)
