# Telegram PPPoE Bot (FastAPI) untuk NuxBill

Bot ini menerima webhook Telegram dan mengelola customer PPPoE melalui API NuxBill (`system/api.php`).

## Fitur

- Webhook `POST /webhook` dengan verifikasi `X-Telegram-Bot-Api-Secret-Token`
- Command:
  - `/customer [page]`
  - `/status <username>`
  - `/recharge <username> <paket>`
  - `/activate <username>`
  - `/deactivate <username>`
  - `/help`
- Caching (TTL), retry terbatas, rate limiting, audit log (SQLite)

## Konfigurasi

Salin `.env.example` menjadi `.env` lalu isi nilainya:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_ALLOWED_USER_IDS` (opsional, daftar user id Telegram dipisah koma)
- `NUXBILL_API_URL` (contoh `https://domain/system/api.php`)
- `NUXBILL_USERNAME` / `NUXBILL_PASSWORD`

### Batasi Akses Bot (Allowlist)

Supaya hanya user tertentu yang bisa memakai bot, set `TELEGRAM_ALLOWED_USER_IDS` berisi daftar Telegram user id (angka), dipisah koma.

Contoh:

```env
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

Jika `TELEGRAM_ALLOWED_USER_IDS` dikosongkan, bot akan menerima semua user.

## Menjalankan Lokal

```bash
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dokumentasi OpenAPI tersedia di:
- `http://localhost:8000/docs`

## Set Webhook Telegram

Gunakan Bot API `setWebhook` dengan `secret_token` yang sama dengan `TELEGRAM_WEBHOOK_SECRET`.

Contoh (ganti `BOT_TOKEN`, `PUBLIC_URL`, dan `TELEGRAM_WEBHOOK_SECRET`):

```bash
curl -X POST "https://api.telegram.org/botBOT_TOKEN/setWebhook" \
  -d "url=PUBLIC_URL/webhook" \
  -d "secret_token=TELEGRAM_WEBHOOK_SECRET"
```

## Menjalankan via Docker

```bash
docker compose up --build
```

Pastikan `.env` menyetel `AUDIT_DB_PATH=/data/audit.db` agar audit trail tersimpan pada volume `./data` (lihat [docker-compose.yml](file:///e:/PRibadi/Mufid/my%20Project/phpnuxbill-master/telegram_pppoe_bot/docker-compose.yml)).

## CI: Build Image ke DockerHub

Workflow GitHub Actions sudah disiapkan: [.github/workflows/telegram-pppoe-bot-dockerhub.yml](file:///e:/PRibadi/Mufid/my%20Project/phpnuxbill-master/.github/workflows/telegram-pppoe-bot-dockerhub.yml)

Yang perlu disiapkan di GitHub repo:

- Buat secrets:
  - `DOCKERHUB_USERNAME`
  - `DOCKERHUB_TOKEN` (pakai DockerHub Access Token)
- Push ke branch `main` untuk menghasilkan tag `latest`
- Push tag `v*` (mis. `v0.1.0`) untuk menghasilkan image bertag versi

## Catatan Performa

- `/customer` dipaginasi agar tetap cepat dan konsisten di bawah 10 detik.
