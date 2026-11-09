import os
import re  # Pustaka untuk Regex (pembersihan emoji)
from googleapiclient.discovery import build
import psycopg2
from datetime import datetime, date

# Konfigurasi API dan Database
DEVELOPER_API_KEY = "AIzaSyCqKKrq5-dCjXagD7AbHMZetGvKxvDXAAI"
DB_HOST = "localhost"
DB_NAME = "youtube_mbg"
DB_USER = "postgres"
DB_PASSWORD = "070805"
DB_PORT = "5432"

def clean_text(text):
    """Fungsi untuk membersihkan emoji dan spasi berlebih pada teks komentar"""
    if not text:
        return ""
    # Menghapus karakter emoji / non-ASCII
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    # Merapikan spasi ganda
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_and_load_comments():
    print("Mulai proses ETL komentar YouTube MBG (Filter Hari Ini)...")
    
    # Ambil tanggal hari ini (sesuai tanggal sistem saat skrip berjalan)
    hari_ini = date.today()
    print(f"Target filter tanggal: {hari_ini}")
    
    # 1. Inisialisasi YouTube API Client
    youtube = build('youtube', 'v3', developerKey=DEVELOPER_API_KEY)
    
    # 2. Query pencarian video berdasarkan kata kunci
    search_response = youtube.search().list(
        q="makan bergizi gratis",
        part="id,snippet",
        maxResults=5,         # Jumlah video yang ingin di-crawl
        order="date",         # Memprioritaskan video terbaru
        type="video"
    ).execute()
    
    # Koneksi ke PostgreSQL
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    cursor = conn.cursor()
    
    total_inserted = 0
    total_filtered_out = 0
    
    for search_item in search_response.get('items', []):
        video_id = search_item['id']['videoId']
        
        try:
            # Ambil komentar dari video tersebut
            comment_response = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=50,    # Kapasitas ambil lebih banyak untuk disaring
                order="time",     # Memprioritaskan komentar berdasarkan waktu terbaru
                textFormat="plainText"
            ).execute()
            
            for item in comment_response.get('items', []):
                snippet = item['snippet']['topLevelComment']['snippet']
                
                # --- TRANSFORM & FILTER ---
                tanggal_str = snippet['publishedAt']
                # Konversi format tanggal API ke objek datetime Python
                tanggal = datetime.strptime(tanggal_str, "%Y-%m-%dT%H:%M:%SZ")
                
                # --- FILTER KETAT: HANYA AMBIL KOMENTAR HARI INI ---
                if tanggal.date() != hari_ini:
                    total_filtered_out += 1
                    continue # Lewati komentar jika bukan hari ini
                
                comment_id = item['id']
                author = snippet['authorDisplayName']
                
                raw_komentar = snippet['textDisplay']
                komentar = clean_text(raw_komentar) # Membersihkan emoji
                
                # --- LOAD (Simpan ke PostgreSQL dengan pencegahan duplikasi) ---
                insert_query = """
                    INSERT INTO komentar_youtube (comment_id, author, komentar, tanggal)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (comment_id) DO NOTHING;
                """
                
                cursor.execute(insert_query, (comment_id, author, komentar, tanggal))
                
                # Cek apakah baris benar-benar berhasil dimasukkan (bukan duplikat)
                if cursor.rowcount > 0:
                    total_inserted += 1
                
        except Exception as e:
            print(f"Gagal mengambil komentar untuk video {video_id}: {e}")
            continue
            
    # Commit perubahan dan tutup koneksi
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Proses ETL Selesai.")
    print(f"- Komentar lama/bukan hari ini yang diabaikan: {total_filtered_out}")
    print(f"- Total data baru hari ini yang berhasil dimasukkan: {total_inserted}")

if __name__ == "__main__":
    extract_and_load_comments()