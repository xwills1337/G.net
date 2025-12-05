import json
import psycopg2
import os

def load_data():
    """Загружает координаты из JSON в БД"""
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        DATABASE_URL = "postgresql://postgres:password@localhost:5432/wifinder"
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    total_loaded = 0
    
    # Загружаем Ростелеком
    try:
        with open('address_rt.json', 'r', encoding='utf-8') as f:
            data_rt = json.load(f)
        
        for point in data_rt:
            coords = point.get('координаты', '')
            if coords:
                lat, lon = coords.split()
                cur.execute(
                    "INSERT INTO wifi_points (latitude, longitude, ratings, avg_rating) VALUES (%s, %s, %s, %s)",
                    (float(lat), float(lon), [], 0.0)
                )
                total_loaded += 1
        
        print(f"Ростелеком: {len(data_rt)} точек")
    except Exception as e:
        print(f"Ошибка загрузки Ростелеком: {e}")
    
    # Загружаем Домру
    try:
        with open('address_dr.json', 'r', encoding='utf-8') as f:
            data_dr = json.load(f)
        
        for point in data_dr:
            coords = point.get('координаты', '')
            if coords:
                lat, lon = coords.split()
                cur.execute(
                    "INSERT INTO wifi_points (latitude, longitude, ratings, avg_rating) VALUES (%s, %s, %s, %s)",
                    (float(lat), float(lon), [], 0.0)
                )
                total_loaded += 1
        
        print(f"Домру: {len(data_dr)} точек")
    except Exception as e:
        print(f"Ошибка загрузки Домру: {e}")
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"Всего загружено точек: {total_loaded}")

if __name__ == "__main__":
    load_data()