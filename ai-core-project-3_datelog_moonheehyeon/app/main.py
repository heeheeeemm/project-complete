"""6 · 7단계 — 라우터를 붙이고, 화면(index.html)이 부를 수 있게 CORS 를 연다

실행 (1일차 폴더에서, app 폴더 바깥):
    uvicorn app.main:app --reload

화면은 터미널을 하나 더 열어 띄운다:
    python serve_frontend.py       →  http://localhost:5500
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / '.env')
from .api import plans, chat, logs, cinemas, showtimes
from .itineraries import router as itineraries_router

app = FastAPI(title="DateLog")

app.add_middleware(              
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plans.router)   
app.include_router(chat.router)
app.include_router(logs.router)
app.include_router(cinemas.router)
app.include_router(showtimes.router)
app.include_router(itineraries_router)


@app.get('/api/hero-image', include_in_schema=False)
def hero_image():
    return FileResponse(Path(__file__).resolve().parent.parent / '딸기케익.jpg', media_type='image/jpeg')


@app.exception_handler(Exception)
async def internal_error(request, error):
    return JSONResponse(status_code=500, content={'detail': '요청을 처리하지 못했습니다. 서버 설정을 확인하고 다시 시도해 주세요.'})
