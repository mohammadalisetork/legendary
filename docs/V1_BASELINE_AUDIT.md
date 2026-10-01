# V1 Baseline Audit

این سند وضعیت فنی شاخه `baseline/v1-regression-hardened` را در Step 0 ثبت می‌کند. مبنا آخرین `main` موجود در GitHub با commit `2b2d825e9f66c866d090251c8f9610c7ee582b36` بوده است. هیچ دسترسی یا مقایسه‌ای با محیط عملیاتی انجام نشده و هیچ قابلیت V2 در این مرحله پیاده‌سازی نشده است.

## معماری فعلی

- مونولیت ماژولار Django با صفحات server-rendered، قالب‌های HTML، CSS و JavaScript خالص
- احراز هویت session-based، حفاظت CSRF، Argon2 و اجبار تغییر رمز اولیه
- مدل کاربر سفارشی با سه نقش سراسری `USER`، `REQUEST_MANAGER` و `ADMIN`
- کنترل دسترسی درخواست‌ها در توابع `accessible_request` و `manager_scope`
- کاتالوگ شامل Category، Service و ServiceFormField؛ فرم پویا بر اساس تعریف فیلدهای هر خدمت ساخته می‌شود
- پاسخ فرم پویا در `Request.request_data` به‌صورت JSON ذخیره می‌شود
- مکالمه در `RequestResponse`، فایل در `Attachment` و یادداشت محرمانه در `InternalNote` ذخیره می‌شود
- تاریخچه درخواست و لاگ مدیریتی به‌ترتیب در `RequestHistory` و `ActivityLog` ثبت می‌شوند
- workflow وضعیت در enum و جدول انتقال داخل مدل `Request` تعریف شده است
- زمان پاسخ و تحویل هنگام ثبت نهایی ذخیره می‌شود؛ زمان عملیاتی با تقویم کاری و رویدادهای توقف به‌صورت پویا محاسبه می‌شود
- تاریخ داخلی میلادی است و ورودی/نمایش جلالی در لایه رابط انجام می‌شود
- پنل Django Admin برای کاربر، کاتالوگ، فیلد فرم، تقویم و تنظیمات پایه استفاده می‌شود
- فایل‌ها روی volume محلی پایدار یا S3-compatible قابل ذخیره‌اند
- startup کانتینر: انتظار برای دیتابیس، migration، seed تکرارپذیر، collectstatic، ساخت مدیر اولیه و اجرای Gunicorn

## استک فنی

- Python 3.12
- Django 5.2.17 و Django ORM
- PostgreSQL 17 در Compose؛ SQLite فقط برای توسعه و آزمون محلی
- Gunicorn 23 و WhiteNoise
- Argon2، `django-storages` و boto3
- Dockerfile چندمرحله‌ای و Docker Compose

## مسائل شناخته‌شده و اصلاحات Step 0

### مکالمه و پیوست درخواست

باگ تاریخی 404 روی آخرین `main` بازتولید نشد. در پیاده‌سازی فعلی:

- پیام کاربر و مدیر هر دو به همان Request متصل می‌شوند.
- Attachment همواره Request را نگه می‌دارد و در صورت تعلق به پیام، به RequestResponse نیز متصل است.
- مدیر درخواست فقط درخواست غیرپیش‌نویسِ تخصیص‌یافته به خود، بدون مسئول، یا متعلق به خدمتی با مسئول پیش‌فرض خود را می‌بیند.
- دانلود فایل دوباره مجوز همان Request را کنترل می‌کند.

برای جلوگیری از بازگشت خطا، آزمون رگرسیون یکپارچه اضافه شد که ثبت درخواست، پیام و تصویر کاربر، بازشدن همان درخواست توسط مدیر، مشاهده و دانلود پیوست، پاسخ مدیر، مشاهده پاسخ توسط کاربر و مخفی‌ماندن یادداشت داخلی را بررسی می‌کند. چون باگ بازتولید نشد، کد backend یا دامنه مجوزها تغییر نکرد.

### اندازه دکمه ثبت درخواست

یک پایه محدود و قابل استفاده مجدد برای دکمه‌های کوچک، متوسط و بزرگ اضافه شد. height، padding افقی، اندازه و وزن متن، فاصله آیکون، radius و حالت‌های disabled/loading مشخص شده‌اند. ناحیه اقدام فرم اکنون شامل «انصراف»، «ذخیره پیش‌نویس» و «ثبت نهایی درخواست» است. دکمه اصلی روی دسکتاپ عرض محتوایی دارد و full-width نیست. بازطراحی عمومی V2 انجام نشده است.

### مدیریت کاربر

آزمون پنل مدیریت برای تغییر نقش، فعال‌شدن دسترسی staff متناسب با نقش و غیرفعال‌سازی حساب اضافه شد.

## Verification اجراشده

- نصب کامل وابستگی‌ها از `requirements.txt`: موفق
- `pip check`: موفق
- مجموعه آزمون Django: 24 آزمون، موفق
- آزمون یکپارچه مکالمه، پیوست و RBAC: موفق
- `manage.py check`: موفق
- `makemigrations --check --dry-run`: بدون تغییر جاافتاده
- `compileall`: موفق
- `check --deploy` با تنظیمات production غیرواقعی و بدون اتصال عملیاتی: موفق
- `collectstatic` با storage تولید: موفق، 129 فایل و 387 خروجی post-process
- migration کامل روی دیتابیس خالی SQLite: موفق
- seed کاتالوگ: موفق، 65 خدمت
- ساخت مدیر اولیه با رمز هش‌شده و تغییر اجباری رمز: موفق
- دو اجرای متوالی Gunicorn و `/health`: موفق
- ماندگاری رکورد دیتابیس و فایل پیوست پس از restart: موفق
- parsing فایل Compose و کنترل serviceها و volumeها: موفق

هیچ lint یا type-checker در مخزن پیکربندی نشده است. Docker و Podman در محیط Agent وجود نداشتند؛ بنابراین Docker image build و `docker compose config/up` واقعاً اجرا نشد. PostgreSQL واقعی و S3 آزمایشی نیز در دسترس نبودند. Browser نتوانست به سرویس محلی Agent متصل شود؛ بازبینی بصری یا E2E مرورگری ادعا نمی‌شود.

## تاریخچه migration و ایمنی دیتابیس

تاریخچه migration دست‌نخورده باقی ماند:

1. `0001_initial`: کل مدل V1
2. `0002_loginthrottle`: محدودسازی ورود ناموفق
3. `0003_alter_request_status`: افزودن وضعیت `ON_HOLD`

هیچ migration جدید، reset، squash یا تغییر مخربی در Step 0 ایجاد نشد.

### ریسک‌های مهاجرت آینده

- Category در V1 عملاً Service Family سراسری است و Department ندارد.
- `Request.requesting_unit` و `Request.project` متن آزاد هستند و کلید خارجی Program/Project وجود ندارد.
- Service و Request هیچ Department صریحی ندارند.
- نقش User سراسری و تک‌مقداری است؛ برای RBAC چنداداره‌ای کافی نیست.
- وضعیت و انتقال‌ها داخل کد hardcoded هستند و موتور تأیید چندمرحله‌ای وجود ندارد.
- زمان‌های SLA روی Service سراسری‌اند و به Department، دوره یا نوع درخواست وابسته نیستند.
- تنها یک تقویم کاری فعال عملاً مبنای محاسبه است.
- `request_data` JSON به کلیدهای فرم فعلی متکی است و نسخه یا snapshot مستقل از schema فرم ندارد؛ تغییر نام یا حذف فیلد می‌تواند خوانایی تاریخی را دشوار کند.
- نام و تعریف Service در Request snapshot نشده است؛ رکورد تاریخی همچنان به نسخه ویرایش‌شده Service اشاره می‌کند.
- حذف RequestResponse به‌صورت cascade رکورد Attachment مرتبط را حذف می‌کند، اما پاک‌سازی فیزیکی object storage نیازمند سیاست جداگانه است.
- فایل‌ها بر اساس پسوند و حجم اعتبارسنجی می‌شوند؛ antivirus/content inspection وجود ندارد.

## ملاحظات معماری V2

مسیر تکامل هدف باید به‌صورت زیر مدل شود:

`Request → Program / Project → Department → Service Family → Service`

پیشنهاد مهاجرت افزایشی و غیرمخرب:

1. موجودیت‌های Department، Program و Project ابتدا با FKهای nullable اضافه شوند.
2. Categoryهای موجود به‌عنوان Service Familyهای اداره توسعه بازار نگاشت شوند.
3. Serviceهای فعلی به Department پیش‌فرض «توسعه بازار» متصل شوند.
4. Requestهای تاریخی Department خود را از Service زمان مهاجرت دریافت کنند، اما فیلدهای متنی `requesting_unit` و `project` برای حفظ snapshot تاریخی حذف نشوند.
5. نگاشت Program از `requesting_unit` و Project از متن `project` فقط با جدول mapping تأییدشده انجام شود؛ تطبیق خودکار قطعی امن نیست.
6. نقش سراسری User به Membership/RoleAssignment محدود به Department، Program و Project تکامل یابد.
7. workflow و تأییدها به تعریف نسخه‌دار، transition و approval-instance جدا منتقل شوند.
8. تعریف فرم و Service برای درخواست‌های تاریخی snapshot یا version شود.
9. قواعد SLA، تقویم و صف رسیدگی در سطح Department/Service نسخه‌دار شوند.

کلید سهمیه اولویت در V2 نباید فقط Program باشد. قید منطقی و یکتای تخصیص باید دقیقاً این ابعاد را داشته باشد:

`Program × Department × Priority × Allocation Period`

مصرف سهمیه باید با ledger یا reservation اتمیک ثبت شود تا سهمیه یک اداره بر اداره دیگر اثر نگذارد و رقابت هم‌زمان موجب مصرف دوباره نشود.

## نقاط اتصال مناسب برای V2

- مدل‌های دامنه: `portal/models.py` با migrationهای افزایشی
- سیاست دسترسی: جایگزینی تدریجی `User.role` و `manager_scope` با policy/service مستقل و scoped
- فرم‌ها و import کاتالوگ: service layer جدا بالای Service و ServiceFormField
- workflow و approval: سرویس دامنه جدا به‌جای گسترش مستقیم `Request.TRANSITIONS`
- تحلیل و گزارش: query/service layer یا read model مستقل؛ محاسبات سنگین داخل template/model property توسعه داده نشوند
- PDF و Excel: job/serviceهای خروجی جدا با مجوز همان Request/Department
- Design System: توکن‌ها و component classهای نسخه‌دار؛ پایه button این Step 0 فقط آغاز کوچک V1 است

## محدودیت‌ها

- محیط production، دیتابیس production و patchهای DevOps در دسترس نبودند و بررسی نشدند.
- نتیجه فقط درباره GitHub baseline و محیط آزمون محلی معتبر است.
- Docker image، PostgreSQL واقعی، S3 و reverse proxy واقعی تأیید نشده‌اند.
- هیچ قابلیت V2 در این شاخه وجود ندارد.
