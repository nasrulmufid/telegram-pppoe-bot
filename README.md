# Telegram PPPoE Bot (FastAPI) untuk NuxBill

Bot ini menerima webhook Telegram dan mengelola customer PPPoE melalui API NuxBill (`system/api.php`).

## Fitur

- Webhook `POST /webhook` dengan verifikasi `X-Telegram-Bot-Api-Secret-Token`
- Command:
  - `/customer [page]`
  - `/status <username>`
  - `/recharge`
  - `/activate <username>`
  - `/deactivate <username>`
  - `/help`
  - `/start`
- Caching (TTL), retry terbatas, rate limiting, audit log (SQLite)

## Konfigurasi

Salin `.env.example` menjadi `.env` lalu isi nilainya:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_ALLOWED_USER_IDS` (opsional, daftar user id Telegram dipisah koma)
- `IP_PUBLIC` (opsional, wajib jika fitur Remote ONU dipakai)
- `PORT_ONU` (opsional, port publik untuk Remote ONU)
- `COMMENT_FIREWALL` (opsional, comment rule NAT MikroTik)
- `MIKROTIK_HOST` (opsional, wajib jika fitur Remote ONU dipakai)
- `MIKROTIK_USERNAME` / `MIKROTIK_PASSWORD` (opsional, wajib jika fitur Remote ONU dipakai)
- `MIKROTIK_PORT` (opsional, default 8728)
- `NUXBILL_API_URL` (contoh `https://domain/system/api.php`)
- `NUXBILL_USERNAME` / `NUXBILL_PASSWORD`

### Batasi Akses Bot (Allowlist)

Supaya hanya user tertentu yang bisa memakai bot, set `TELEGRAM_ALLOWED_USER_IDS` berisi daftar Telegram user id (angka), dipisah koma.

Contoh:

```env
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

Jika `TELEGRAM_ALLOWED_USER_IDS` dikosongkan, bot akan menerima semua user.

### Remote ONU via MikroTik

Fitur ini menambahkan tombol **Remote ONU** pada output `/status <username>`.

Saat tombol ditekan, bot akan membuat atau mengedit rule MikroTik pada `/ip firewall nat` berdasarkan `COMMENT_FIREWALL`:
- chain: `dstnat`
- protocol: `tcp`
- dst-address: `IP_PUBLIC`
- dst-port: `PORT_ONU`
- action: `dst-nat`
- to-addresses: IPTR069 (Virtual Parameter GenieACS)
- to-ports: `80`

Setelah rule siap, bot mengirim link `http://IP_PUBLIC:PORT_ONU` untuk dibuka di browser.

Jika variabel env Remote ONU tidak diisi, tombol **Remote ONU** tidak akan ditampilkan.

### Integrasi GenieACS (Ganti SSID/Password)

Bot terintegrasi dengan GenieACS NBI memakai Basic Auth.

- Mapping customer → device: bot mencari device GenieACS berdasarkan Virtual Parameter `pppoeUsername` yang sama dengan field `pppoe_username` dari NuxBill.
- Tombol di detail customer `/customer`: **Ganti SSID** dan **Ganti Password**.
- Parameter yang diubah (TR-069):
  - `InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID`
  - `InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.KeyPassphrase`
- Setelah nilai dikonfirmasi, bot mengirim task `setParameterValues` ke endpoint `/devices/<device_id>/tasks?connection_request`.

### IPTR069 untuk Remote ONU

Remote ONU menggunakan IP tujuan dari GenieACS Virtual Parameter `IPTR069` (bukan dari IP PPPoE NuxBill).

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
