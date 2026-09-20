import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import router
from app.core.db import initialize_db
from app.core.settings import settings
from app.services.sam2_runtime import sam2_runtime
@asynccontextmanager
async def lifespan(app:FastAPI):
    initialize_db()
    threading.Thread(target=sam2_runtime.initialize,name='sam2-init',daemon=True).start()
    yield
    sam2_runtime.shutdown()
app=FastAPI(title='Sewer SAM2 Annotator API',version='2.0.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin,'http://localhost:8092'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
app.include_router(router)
@app.get('/health')
def health():
    sam2=sam2_runtime.status()
    return {'status':'ok','model':settings.model_id,'sam2_ready':sam2['ready'],'sam2_loading':sam2['loading'],'sam2_error':sam2['error']}
