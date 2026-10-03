# کاتالوگ خدمات و مدیریت درخواست‌ها

پرتال داخلی فارسی برای کاتالوگ خدمات اداره توسعه بازار، ثبت و پیگیری درخواست، گردش‌کار رسیدگی، پیام‌ها، اعلان‌ها، زمان‌بندی کاری و مدیریت سامانه.

## استک فنی

- Python 3.12، Django 5.2 و Gunicorn
- قالب‌های سمت سرور Django، HTML5، CSS3 و JavaScript
- PostgreSQL و Django ORM
- Docker و Docker Compose؛ ذخیره فایل روی volume پایدار یا S3-compatible

## نیازمندی‌ها

- Docker و Docker Compose
- PostgreSQL 14 یا جدیدتر در استقرار بدون Compose
- Reverse proxy دارای TLS در محیط عملیاتی

## راه‌اندازی با Docker

```bash
cp deploy/production.env.example .env
# مقادیر محرمانه، دامنه و گذرواژه‌ها را در .env تغییر دهید
docker compose up --build -d
curl http://127.0.0.1:8000/health
```

ورودی کانتینر به‌ترتیب اتصال پایگاه داده، migration، seed کاتالوگ، جمع‌آوری فایل‌های ایستا و ایجاد مدیر اولیه را اجرا می‌کند. seed تکرارپذیر است و خدمات ویرایش‌شده را بازنویسی نمی‌کند.

ترتیب تحویل عملیاتی: clone مخزن، ساخت `.env` تولید، تنظیم PostgreSQL و فضای فایل پایدار، اجرای Compose، کنترل migration و مدیر اولیه، اتصال reverse proxy و دامنه، سپس بررسی `/health`.

## متغیرهای محیطی

نمونهٔ محیط محلی در `.env.example` و نمونهٔ placeholder تولید در `deploy/production.env.example` است. در محیط عملیاتی حداقل `APP_ENV`، `APP_URL`، `AUTH_SECRET`، `ALLOWED_HOSTS`، `CSRF_TRUSTED_ORIGINS` و تنظیمات پایگاه داده و ذخیره‌سازی را تعیین کنید. اتصال پایگاه داده از طریق `DATABASE_URL` یا مجموعه کامل متغیرهای `POSTGRES_*` پذیرفته می‌شود. Compose از روش دوم استفاده می‌کند تا گذرواژه‌های دارای نویسه‌های ویژه بدون نیاز به URL-encoding معتبر باشند. مقدار واقعی رمز یا کلید را وارد مخزن نکنید.

برای S3-compatible مقدار `FILE_STORAGE_TYPE=s3` و متغیرهای `S3_ENDPOINT`، `S3_BUCKET`، `S3_ACCESS_KEY` و `S3_SECRET_KEY` را تنظیم کنید. در حالت `local` مسیر `UPLOAD_PATH` باید روی volume پایدار قرار گیرد.

## مدیر اولیه

در نخستین اجرا، متغیرهای `INITIAL_ADMIN_USERNAME` و `INITIAL_ADMIN_PASSWORD` مدیر را می‌سازند. گذرواژه موقت است و کاربر در نخستین ورود مجبور به تغییر آن می‌شود. پس از ایجاد حساب، حذف این دو متغیر از محیط توصیه می‌شود.

ساخت دستی کنترل‌شده:

```bash
docker compose exec web python manage.py create_initial_admin
```

## عملیات پایگاه داده

```bash
python manage.py migrate
python manage.py seed_catalog
```

پشتیبان‌گیری باید PostgreSQL و فضای فایل‌ها را با یک نقطه زمانی سازگار پوشش دهد. برای PostgreSQL از `pg_dump` و برای volume محلی از snapshot یا backup فایل استفاده کنید. سیاست نگهداری و آزمون بازیابی بر عهده زیرساخت است.

## Reverse proxy و پایش

نمونه Nginx در `deploy/nginx.conf.example` است. TLS، DNS و گواهی در لایه زیرساخت تنظیم می‌شوند. مسیر `/health` وضعیت برنامه و اتصال پایگاه داده را بدون افشای تنظیمات گزارش می‌کند.

## اجرای محلی آزمون‌ها

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_catalog
.venv/bin/python manage.py test
```

## مرور محلی Release 2.5

برای اجرای محیط محلی UAT با دادهٔ نمونه، حساب‌های نمایشی، سناریوهای نقش‌محور و خروجی‌های داشبورد، راهنمای [LOCAL_UAT_GUIDE](docs/LOCAL_UAT_GUIDE.md) را دنبال کنید. فرمان `seed_demo --confirm-local-only` فقط در حالت توسعه/آزمون محلی فعال است و برای دیتابیس تولیدی مجاز نیست.
