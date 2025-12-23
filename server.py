from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
import psycopg2
import folium
import uvicorn
import os


API_KEY_NAME = "x-api-key"
API_KEY = os.environ["API_KEY"]


class RatingRequest(BaseModel):
    rating: int


app = FastAPI()


def get_real_client_ip(request):
    """
    Получает реальный IP клиента на Railway
    Формат: "клиентский-ip, railway-proxy-ip, ..."
    """
    if "x-forwarded-for" in request.headers:
        forwarded = request.headers["x-forwarded-for"]
        # Разделяем цепочку IP: клиент, прокси1, прокси2, ...
        ips = [ip.strip() for ip in forwarded.split(",")]
        if ips:
            return ips[0]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"

limiter = Limiter(key_func=get_real_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def verify_api_key_middleware(request: Request, call_next):
    api_key = request.headers.get(API_KEY_NAME)
    
    if not api_key:
        return JSONResponse(
            status_code=401,
            content={"error": "API key is missing"}
        )
    
    if api_key != API_KEY:
        return JSONResponse(
            status_code=403,
            content={"error": "Invalid API key"}
        )
    
    return await call_next(request)


def get_db():
    """Подключение к БД"""
    DATABASE_URL = os.environ.get('DATABASE_URL2')
    if not DATABASE_URL:
        DATABASE_URL = "postgresql://postgres:password@localhost:5432/wifinder"
    return psycopg2.connect(DATABASE_URL)


def create_map(wifi_points):
    """Создание карты с Wi-Fi точками"""
    # Если есть точки - центрируем по средним координатам, иначе по умолчанию
    if wifi_points:
        avg_lat = sum(p['lat'] for p in wifi_points) / len(wifi_points)
        avg_lon = sum(p['lon'] for p in wifi_points) / len(wifi_points)
    else:
        avg_lat, avg_lon = 53.2020, 50.1590  # Координаты по умолчанию
    
    # Создаем карту Folium
    m = folium.Map(
        location=[avg_lat, avg_lon],  # Центр карты
        zoom_start=10,                # Уровень приближения
        tiles='OpenStreetMap'         # Стиль карты
    )
    
    # Добавляем точки на карту
    for point in wifi_points:
        rating = point.get('rating', 0)    
        color = 'gray'
        if rating > 0 and rating <= 2.5:
            color = 'darkorange'
        elif rating > 2.5 and rating <= 4.5:
            color = 'blue'
        elif rating > 4.5:
            color = 'green'
        
        folium.CircleMarker(
            location=[point['lat'], point['lon']],  # Координаты точки
            radius=4,                               # Размер кружка
            color=color,                            # Цвет границы
            fillColor=color,                        # Цвет заливки  
            fillOpacity=0.7,                        # Прозрачность заливки
            weight=1                                # Толщина границы
        ).add_to(m)
    
    return m


@app.get("/")
async def main_page():
    """Главная страница с картой"""
    # Получаем точки из БД
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT latitude, longitude, avg_rating FROM wifi_points")
    
    # Преобразуем в нужный формат для функции create_map
    wifi_points = []
    for row in cur.fetchall():
        wifi_points.append({
            "lat": float(row[0]),
            "lon": float(row[1]),
            "rating": float(row[2]) if row[2] is not None else None
        })
    
    cur.close()
    conn.close()
    
    # Создаем карту
    map_obj = create_map(wifi_points)
    
    # Возвращаем HTML карты
    return HTMLResponse(content=map_obj._repr_html_())


@app.get("/api/data")
async def get_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, latitude, longitude, address, avg_rating FROM wifi_points")
    points = [{
        "id": r[0], 
        "lat": float(r[1]), 
        "lon": float(r[2]),
        "address": r[3] if r[3] else "",
        "rating": float(r[4]) if r[4] else 0.0
    } for r in cur.fetchall()]
    cur.close()
    conn.close()
    return {"points": points}


@app.get("/point/{point_id}")
async def get_point_by_id(point_id: int):
    """Возвращает информацию точки по ID"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT latitude, longitude, address, avg_rating FROM wifi_points WHERE id = %s", (point_id,))
    
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Точка не найдена")
    
    return {
        "id": point_id,
        "latitude": float(row[0]),
        "longitude": float(row[1]),
        "address": row[2] if row[2] else "",
        "rating": float(row[3]) if row[3] else 0.0
    }


@app.post("/api/rate/{point_id}")
@limiter.limit("1/10 minutes")
async def rate_point(request: Request, point_id: int):
    import json
    body = await request.body()
    data = json.loads(body)
    
    # Проверяем наличие ключа rating
    if "rating" not in data:
        return JSONResponse(
            status_code=400,
            content={"error": "Rating field is required"}
        )
    
    rating = data["rating"]
    
    # Проверяем тип и значение
    if not isinstance(rating, int):
        return JSONResponse(
            status_code=400,
            content={"error": "Rating must be an integer"}
        )
    
    if rating < 1 or rating > 5:
        return JSONResponse(
            status_code=400,
            content={"error": "Rating must be between 1 and 5"}
        )
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT ratings FROM wifi_points WHERE id = %s", (point_id,))
    row = cur.fetchone()
    
    if not row:
        cur.close()
        conn.close()
        return {"error": "Точка не найдена"}
    
    ratings = row[0] if row[0] else []
    ratings.append(rating)
    avg = sum(ratings) / len(ratings)
    
    cur.execute("""
        UPDATE wifi_points 
        SET ratings = %s, avg_rating = %s 
        WHERE id = %s
    """, (ratings, round(avg, 2), point_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"ok": True, "point_id": point_id}


@app.get("/test-db")
async def test_db():
    """Тест только подключения к БД"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return {"db_status": "ok", "test": result[0]}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(" DB ERROR:", error_details)
        return {"db_status": "error", "error": str(e), "traceback": error_details}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
