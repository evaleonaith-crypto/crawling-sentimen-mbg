
import logging
import time
from datetime import datetime, date, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# 1. KONFIGURASI
# ============================================================

API_KEY = "AIzaSyA7gbMnY9--NagvS2sOuPsb0TeGt_f_pYI"

DB_CONFIG = {
    "host": "localhost",
    "database": "youtube_mbg",
    "user": "postgres",
    "password": "7805",
    "port": "5432"
}

WIB = ZoneInfo("Asia/Jakarta")

KEYWORDS = [
    "makan bergizi gratis",
    "MBG Indonesia",
    "keracunan MBG"
]

POLL_INTERVAL_MINUTES = 5
SEARCH_REFRESH_MINUTES = 15

# Maksimal 3 halaman pencarian untuk setiap kata kunci.
# Satu halaman maksimal 50 video.
MAX_SEARCH_PAGES = 3

LOG_FILE = "etl_mbg.log"


# ============================================================
# 2. KONFIGURASI LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# ============================================================
# 3. FUNGSI WAKTU
# ============================================================

def waktu_sekarang():
    return datetime.now(WIB)


def waktu_ke_utc(dt):
    return dt.astimezone(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


# ============================================================
# 4. KONEKSI YOUTUBE
# ============================================================

def koneksi_youtube():
    return build(
        "youtube",
        "v3",
        developerKey=API_KEY
    )


# ============================================================
# 5. KONEKSI POSTGRESQL
# ============================================================

def koneksi_database():
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
# 6. MENCARI VIDEO YANG DIUNGGAH HARI INI
# ============================================================

def cari_video_hari_ini(youtube, awal_hari, batas_pencarian):

    daftar_video = {}

    published_after = waktu_ke_utc(awal_hari)
    published_before = waktu_ke_utc(batas_pencarian)

    for keyword in KEYWORDS:

        logger.info(f"Mencari video: {keyword}")

        page_token = None

        for halaman in range(MAX_SEARCH_PAGES):

            try:
                request = youtube.search().list(
                    part="id,snippet",
                    q=keyword,
                    type="video",
                    order="date",
                    publishedAfter=published_after,
                    publishedBefore=published_before,
                    maxResults=50,
                    pageToken=page_token
                )

                response = request.execute()

                for item in response.get("items", []):

                    video_id = item["id"]["videoId"]

                    daftar_video[video_id] = {
                        "judul": item["snippet"]["title"],
                        "tanggal_upload": item["snippet"]["publishedAt"]
                    }

                page_token = response.get("nextPageToken")

                if not page_token:
                    break

            except HttpError as e:
                logger.error(
                    f"Gagal mencari video untuk '{keyword}': {e}"
                )
                break

    logger.info(
        f"Total video unik ditemukan: {len(daftar_video)}"
    )

    return daftar_video


# ============================================================
# 7. MENYIMPAN KOMENTAR LANGSUNG KE POSTGRESQL
# ============================================================

def simpan_komentar(cursor, connection, item):

    komentar = item["snippet"]["topLevelComment"]

    comment_id = komentar["id"]
    author = komentar["snippet"].get(
        "authorDisplayName", "Tidak diketahui"
    )
    teks = komentar["snippet"].get("textDisplay", "")

    tanggal_utc = datetime.fromisoformat(
        komentar["snippet"]["publishedAt"].replace(
            "Z", "+00:00"
        )
    )

    tanggal_wib = tanggal_utc.astimezone(WIB)

    # Simpan waktu WIB sebagai timestamp tanpa timezone.
    tanggal_database = tanggal_wib.replace(tzinfo=None)

    try:

        cursor.execute(
            """
            INSERT INTO public.komentar_youtube
            (comment_id, author, komentar, tanggal)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (comment_id) DO NOTHING
            RETURNING comment_id
            """,
            (
                comment_id,
                author,
                teks,
                tanggal_database
            )
        )

        hasil = cursor.fetchone()

        # Commit langsung setelah komentar ditemukan dan dimasukkan.
        connection.commit()

        if hasil:
            logger.info(
                f"KOMENTAR BARU TERSIMPAN | "
                f"{tanggal_wib.strftime('%H:%M:%S')} | {comment_id}"
            )
            return 1

        logger.info(f"Komentar duplikat dilewati: {comment_id}")
        return 0

    except Exception as e:

        connection.rollback()

        logger.error(
            f"Gagal menyimpan komentar {comment_id}: {e}"
        )

        return 0


# ============================================================
# 8. MENGAMBIL KOMENTAR DALAM RENTANG 21.00-22.00 WIB
# ============================================================

def ambil_komentar_video(
    youtube,
    cursor,
    connection,
    video_id,
    awal_sesi,
    akhir_sesi
):

    jumlah_baru = 0
    page_token = None

    while waktu_sekarang() < akhir_sesi:

        try:

            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                order="time",
                textFormat="plainText",
                pageToken=page_token
            )

            response = request.execute()

            items = response.get("items", [])

            if not items:
                break

            perlu_berhenti = False

            for item in items:

                komentar = item["snippet"]["topLevelComment"]

                published_at = datetime.fromisoformat(
                    komentar["snippet"]["publishedAt"].replace(
                        "Z", "+00:00"
                    )
                )

                tanggal_wib = published_at.astimezone(WIB)

                # Karena komentar diurutkan dari yang terbaru,
                # komentar sebelum awal sesi berarti halaman berikutnya
                # juga lebih lama.
                if tanggal_wib < awal_sesi:
                    perlu_berhenti = True
                    break

                # Hanya komentar dalam rentang sesi yang disimpan.
                if awal_sesi <= tanggal_wib < akhir_sesi:

                    jumlah_baru += simpan_komentar(
                        cursor,
                        connection,
                        item
                    )

            if perlu_berhenti:
                break

            page_token = response.get("nextPageToken")

            if not page_token:
                break

        except HttpError as e:

            pesan = str(e)

            if "commentsDisabled" in pesan:
                logger.warning(
                    f"Komentar dinonaktifkan pada video: {video_id}"
                )
            else:
                logger.error(
                    f"Gagal mengambil komentar video "
                    f"{video_id}: {e}"
                )

            break

        except Exception as e:

            logger.error(
                f"Kesalahan saat memproses video {video_id}: {e}"
            )
            break

    return jumlah_baru


# ============================================================
# 9. PROSES ETL BERULANG 21.00-22.00 WIB
# ============================================================

def jalankan_etl():

    sekarang = waktu_sekarang()

    tanggal_hari_ini = sekarang.date()

    awal_hari = datetime.combine(
        tanggal_hari_ini,
        dt_time(0, 0),
        tzinfo=WIB
    )

    awal_sesi = datetime.combine(
        tanggal_hari_ini,
        dt_time(21, 0),
        tzinfo=WIB
    )

    akhir_sesi = datetime.combine(
        tanggal_hari_ini,
        dt_time(22, 0),
        tzinfo=WIB
    )

    # Jika script dijalankan sebelum pukul 21.00,
    # tunggu sampai pukul 21.00.
    if sekarang < awal_sesi:

        logger.info("Menunggu sampai pukul 21.00 WIB...")

        while waktu_sekarang() < awal_sesi:
            time.sleep(1)

    if waktu_sekarang() >= akhir_sesi:

        logger.warning(
            "Waktu sesi 21.00-22.00 sudah berakhir. "
            "ETL tidak dijalankan."
        )
        return

    logger.info("=" * 60)
    logger.info("MULAI PROSES ETL KOMENTAR YOUTUBE MBG")
    logger.info(f"Tanggal filter WIB: {tanggal_hari_ini}")
    logger.info("Rentang komentar: 21.00-22.00 WIB")
    logger.info("Interval crawling: setiap 5 menit")
    logger.info("=" * 60)

    youtube = koneksi_youtube()

    connection = None
    cursor = None

    try:

        connection = koneksi_database()
        cursor = connection.cursor()

        total_tersimpan = 0
        total_video_diperiksa = 0

        daftar_video = {}
        waktu_pencarian_berikutnya = awal_sesi

        nomor_siklus = 0

        while waktu_sekarang() < akhir_sesi:

            waktu_siklus_mulai = time.monotonic()

            nomor_siklus += 1

            logger.info(
                f"MEMULAI SIKLUS CRAWLING KE-{nomor_siklus}"
            )

            sekarang = waktu_sekarang()

            # Perbarui daftar video setiap 15 menit.
            if (
                not daftar_video
                or sekarang >= waktu_pencarian_berikutnya
            ):

                hasil_video = cari_video_hari_ini(
                    youtube,
                    awal_hari,
                    sekarang
                )

                daftar_video.update(hasil_video)

                waktu_pencarian_berikutnya = (
                    sekarang
                    + timedelta(minutes=SEARCH_REFRESH_MINUTES)
                )

            logger.info(
                f"Jumlah video target saat ini: {len(daftar_video)}"
            )

            # Periksa komentar dari seluruh video target.
            for video_id, informasi in list(daftar_video.items()):

                if waktu_sekarang() >= akhir_sesi:
                    break

                logger.info(
                    f"Memeriksa komentar video: "
                    f"{informasi['judul']}"
                )

                total_video_diperiksa += 1

                jumlah = ambil_komentar_video(
                    youtube,
                    cursor,
                    connection,
                    video_id,
                    awal_sesi,
                    akhir_sesi
                )

                total_tersimpan += jumlah

            logger.info(
                f"Siklus ke-{nomor_siklus} selesai. "
                f"Komentar baru tersimpan: {total_tersimpan}"
            )

            if waktu_sekarang() >= akhir_sesi:
                break

            # Tunggu sampai jadwal pemeriksaan berikutnya.
            durasi_siklus = (
                time.monotonic() - waktu_siklus_mulai
            )

            waktu_tunggu = max(
                0,
                POLL_INTERVAL_MINUTES * 60 - durasi_siklus
            )

            sisa_waktu = (
                akhir_sesi - waktu_sekarang()
            ).total_seconds()

            time.sleep(min(waktu_tunggu, max(0, sisa_waktu)))

        logger.info("=" * 60)
        logger.info("PROSES ETL SELESAI")
        logger.info(
            f"Total video diperiksa: {total_video_diperiksa}"
        )
        logger.info(
            f"Total komentar baru tersimpan: {total_tersimpan}"
        )
        logger.info("Waktu akhir: 22.00 WIB")
        logger.info("=" * 60)

    finally:

        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

        logger.info("Koneksi database ditutup.")


# ============================================================
# 10. PROGRAM UTAMA
# ============================================================

if __name__ == "__main__":

    try:
        jalankan_etl()

    except Exception as e:

        logger.exception(
            f"ETL mengalami kesalahan: {e}"
        )
