"""Isolated inference demo; deliberately exposes no catalog, review or crawler endpoints."""
import os
from pathlib import Path
from threading import Lock
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal
from cement.inference import infer, ROOT

app=FastAPI(title='Cement model demo',docs_url=None,redoc_url=None)
lock=Lock()

@app.middleware('http')
async def bound_request(request, call_next):
    from starlette.responses import JSONResponse
    if request.method=='POST':
        total=0; chunks=[]
        async for chunk in request.stream():
            total+=len(chunk)
            if total>65536: return JSONResponse({'detail':'Request too large'},status_code=413)
            chunks.append(chunk)
        request._body=b''.join(chunks)
    return await call_next(request)

class Input(BaseModel):
    text: str = Field(min_length=1,max_length=12000)
    method: Literal['classifier','retrieval']='retrieval'
    use_reranker: bool=False

@app.get('/api/model-status')
def status():
    return {'available':True,'classifier':(ROOT/'models/classifier.joblib').exists(),
            'retrieval':True,'reranker':os.getenv('CEMENT_ENABLE_RERANKER','1')=='1',
            'stores_input':False}

@app.post('/api/infer')
def predict(value:Input):
    if value.use_reranker and os.getenv('CEMENT_ENABLE_RERANKER','1')!='1':
        raise HTTPException(400,'Reranker disabled on this host')
    if not value.text.strip(): raise HTTPException(422,'Text is blank')
    if not lock.acquire(blocking=False): raise HTTPException(429,'Model busy; retry later')
    try:
        return infer(value.text,value.method,value.use_reranker)
    except FileNotFoundError:
        raise HTTPException(503,'Self-trained model is not installed')
    except Exception:
        raise HTTPException(503,'Model unavailable; check server setup')
    finally: lock.release()

app.mount('/',StaticFiles(directory=ROOT/'docs',html=True),name='showcase')
