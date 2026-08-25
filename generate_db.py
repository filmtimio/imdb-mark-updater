import urllib.request
import gzip
import sqlite3
import os
import time

URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
GZ_FILE = "title.ratings.tsv.gz"
DB_FILE = "ratings.sqlite"

# 1. 容错下载：增加 3 次重试机制
def download_with_retry(url, filename, retries=3):
    for attempt in range(retries):
        try:
            print(f"开始下载 (尝试 {attempt + 1}/{retries})...")
            urllib.request.urlretrieve(url, filename)
            print("下载成功！")
            return
        except Exception as e:
            print(f"下载失败: {e}")
            if attempt < retries - 1:
                time.sleep(5) # 等待 5 秒后重试
            else:
                raise Exception("下载彻底失败，已退出任务。")

def build_database():
    download_with_retry(URL, GZ_FILE)

    print("准备构建 SQLite 数据库...")
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")
    
    cursor.execute('''
        CREATE TABLE ratings (
            tconst TEXT PRIMARY KEY,
            averageRating REAL,
            numVotes INTEGER
        )
    ''')
    
    print("流式读取并清洗数据...")
    batch_size = 100000
    batch = []
    
    with gzip.open(GZ_FILE, 'rt', encoding='utf-8') as f:
        next(f)  # 跳过表头
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) == 3:
                # 2. 核心防御：过滤 IMDb 特有的 \N 脏数据
                if parts[1] == '\\N' or parts[2] == '\\N':
                    continue
                
                try:
                    batch.append((parts[0], float(parts[1]), int(parts[2])))
                except ValueError:
                    continue # 遇到无法转换的数据直接丢弃，防止崩溃
                
            if len(batch) >= batch_size:
                cursor.executemany("INSERT INTO ratings (tconst, averageRating, numVotes) VALUES (?, ?, ?)", batch)
                batch = []
                
    if batch:
        cursor.executemany("INSERT INTO ratings (tconst, averageRating, numVotes) VALUES (?, ?, ?)", batch)
        
    print("建立索引并压缩数据库体积...")
    cursor.execute("CREATE INDEX idx_tconst ON ratings(tconst);")
    
    conn.commit()
    # 3. 终极优化：清理数据库碎片，确保体积最小
    cursor.execute("VACUUM;")
    conn.close()
    
    # 4. 完整性校验：防止空包或残缺包上传
    size_mb = os.path.getsize(DB_FILE) / (1024 * 1024)
    print(f"数据库构建完毕！最终大小: {size_mb:.2f} MB")
    
    if size_mb < 15: # 目前完整的 IMDb 评分 SQLite 大约 25-35MB
        raise Exception(f"警告：数据库体积异常 ({size_mb:.2f} MB)，可能生成失败，阻止上传！")

if __name__ == "__main__":
    build_database()
