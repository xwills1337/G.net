import psycopg2
import os

def init_database():
    """Создает таблицу в БД (только координаты)"""
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        DATABASE_URL = "postgresql://postgres:password@localhost:5432/wifinder"
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Создаем простую таблицу только с координатами
    cur.execute("DROP TABLE IF EXISTS wifi_points")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wifi_points (
            id SERIAL PRIMARY KEY,
            latitude DECIMAL(10,8) NOT NULL,
            longitude DECIMAL(11,8) NOT NULL,
            ratings INTEGER[] DEFAULT '{}',
            avg_rating DECIMAL(3,2) DEFAULT 0.0  
        )
    """)
    
    # Индекс для быстрого поиска по координатам
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_wifi_location 
        ON wifi_points(latitude, longitude)
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("База данных создана")

if __name__ == "__main__":
    init_database()