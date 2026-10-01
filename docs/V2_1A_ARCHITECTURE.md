# معماری Release 2.1A: Department و Scoped RBAC

این سند تغییرات شاخه `release/2.1a-department-rbac-foundation` را ثبت می‌کند. Release 2.1A تکامل افزایشی V1 است؛ Django، قالب‌های server-rendered، تاریخچه migration و شناسه‌های Request حفظ شده‌اند.

## مدل دامنه

- `Department` واحد سازمانی ارائه‌دهنده خدمت است و با `code` پایدار و مستقل از نام فارسی شناخته می‌شود.
- چرخه عمر Department شامل `DRAFT`، `PUBLISHED`، `DISABLED` و `ARCHIVED` است.
- `Category` در دیتابیس با همان نام فنی قبلی باقی مانده، اما از نظر دامنه «Service Family» است و به یک Department تعلق دارد.
- هر `Service` از طریق Service Family دقیقاً یک Department دارد؛ بنابراین ناسازگاری Service و Service Family از نظر ساختاری ممکن نیست.
- `Service.default_owner` فقط می‌تواند Super Admin یا Request Manager/Department Lead همان Department باشد. این قاعده در validation مدل و فرم Admin اعمال می‌شود.
- `Request.department` رابطه‌ای صریح و غیرnullable است. هنگام ایجاد Request فقط از Service استخراج می‌شود و ورودی کاربر پذیرفته نمی‌شود.
- Department ذخیره‌شده روی Request یک snapshot سازمانی است و با انتقال بعدی Service Family تغییر نمی‌کند.
- فیلدهای قدیمی `requesting_unit` و `project` برای حفظ تاریخچه حذف یا تفسیر مجدد نشده‌اند.

مدل فعلی:

`Department → Category (Service Family) → Service → Request`

مسیر توسعه بعدی بدون حذف داده:

`Request → Program / Project → Department → Service Family → Service`

## نقش و Scope

`RoleAssignment` منبع نقش‌های جدید است و این اجزا را دارد:

- User
- Role
- Scope Type
- Department، فقط برای scope اداره‌ای
- Active state
- Assigned by
- Created/updated timestamps

نقش‌های پیاده‌شده: `REQUEST_MANAGER`، `DEPARTMENT_LEAD`، `SUPERVISOR`، `EXECUTIVE_VIEWER` و `SUPER_ADMIN`. نقش `REQUESTER` در مدل قابل ثبت است، ولی درخواست‌دهندگی فعلاً برای تمام کاربران فعال احراز هویت‌شده برقرار است و عضویت اداره‌ای لازم ندارد.

`scope_type` اکنون `GLOBAL` و `DEPARTMENT` را پشتیبانی می‌کند. Program و Project در 2.2 با FKهای nullable و constraintهای جدید به همین assignment model افزوده می‌شوند؛ policy interface و actionها نیاز به بازنویسی ندارند.

## Policy و تقدم مجوزها

مجوزهای backend در `portal/policies.py` متمرکز شده‌اند. ورودی اصلی policy، User، Action و در صورت نیاز Resource/Department است. پنهان‌کردن دکمه‌ها تنها بهبود UI است و مجوز اصلی در backend دوباره کنترل می‌شود.

ترتیب تقدم:

1. Legacy `ADMIN` و assignment فعال `SUPER_ADMIN` دسترسی کامل دارند. Legacy Admin برای مسیر بازیابی اضطراری حفظ شده است.
2. Assignmentهای فعال جدید برای scopeهای Department و Global منبع authoritative مسیرهای 2.1A هستند.
3. Legacy `REQUEST_MANAGER` فقط وقتی هیچ assignment عملیاتی اداره‌ای ندارد، به‌صورت compatibility fallback مدیر Request در Department توسعه بازار محسوب می‌شود.
4. Legacy `USER` فقط مجوزهای requester و Requestهای متعلق به خودش را دارد.

این قاعده مانع دو منبع متناقض می‌شود: به‌محض ثبت assignment اداره‌ای برای یک Legacy Request Manager، fallback قدیمی دیگر اعمال نمی‌شود.

Actionهای اصلی پیاده‌شده عبارت‌اند از `request.create`، `request.view_own`، `request.view_department`، `request.view_all`، `request.assign`، `request.respond`، `request.change_status`، `request.internal_note` و دسترسی dashboard اداره‌ای. نام‌های action آینده از قبل در policy تعریف شده‌اند، ولی تا زمان پیاده‌سازی قابلیت مربوطه مجوز عملیاتی ایجاد نمی‌کنند.

## ماتریس دسترسی

«رزرو» یعنی مفهوم مجوز تعریف شده اما قابلیت مقصد در این release ساخته نشده است.

| قابلیت | Requester | Request Manager | Department Lead | Supervisor | Executive Viewer | Super Admin |
|---|---:|---:|---:|---:|---:|---:|
| مشاهده Requestهای خود | پیاده | پیاده | پیاده | پیاده | پیاده | پیاده |
| ایجاد Request | پیاده | پیاده | پیاده | پیاده | پیاده | پیاده |
| مشاهده Requestهای Department | خیر | پیاده، با منطق تخصیص V1 | پیاده | همه Departmentها، فقط خواندنی | خیر | پیاده |
| مشاهده همه Departmentها | خیر | خیر | خیر | پیاده، فقط خواندنی | رزرو برای 2.3 | پیاده |
| تخصیص Request | خیر | پیاده در scope خود | پیاده در scope خود | خیر | خیر | پیاده |
| پاسخ عملیاتی | خیر | پیاده در scope خود | پیاده در scope خود | خیر | خیر | پیاده |
| تغییر وضعیت | خیر | پیاده در scope خود | پیاده در scope خود | خیر | خیر | پیاده |
| Internal Note | خیر | پیاده در scope خود | پیاده در scope خود | خیر | خیر | پیاده |
| مدیریت Department | خیر | خیر | رزرو برای 2.1B | خیر | خیر | پیاده در Django Admin |
| مدیریت عضویت Department | خیر | خیر | رزرو برای 2.1B | خیر | خیر | پیاده در Django Admin |
| مدیریت Catalogue | خیر | خیر | رزرو برای 2.1B/2.4 | خیر | خیر | پیاده در Django Admin |
| Dashboard اداره‌ای | خیر | صف عملیاتی فعلی | صف عملیاتی فعلی | فقط خواندنی | خیر | صف عملیاتی فعلی |
| Executive Dashboard | خیر | خیر | خیر | خیر | رزرو برای 2.3 | رزرو برای 2.3 |
| مدیریت کاربران | خیر | خیر | خیر | خیر | خیر | پیاده در Django Admin |
| تنظیمات سراسری | خیر | خیر | خیر | خیر | خیر | پیاده در Django Admin |
| Audit | خیر | خیر | خیر | رزرو | خیر | پیاده در Django Admin |

## مهاجرت Legacy V1

مهاجرت در سه مرحله انجام می‌شود:

1. `0004_department_rbac_schema`: ساخت schema جدید و FKهای nullable.
2. `0005_department_legacy_data`: ایجاد idempotent شش Department، نگاشت تمام Category/Service/Requestهای V1 به `market-development` و ساخت assignment برای Adminها و Request Managerهای قدیمی.
3. `0006_department_constraints`: غیرnullable کردن FKها و افزودن uniquenessهای Department-aware.

تنها Department توسعه بازار `PUBLISHED` است. پنج Department دیگر `DRAFT` هستند و تا ورود کاتالوگ خودشان به کاربران نمایش داده نمی‌شوند. Seed با code پایدار Department کار می‌کند و اجرای دوباره آن Department یا Category تکراری نمی‌سازد.

تست migration روی دیتابیس نماینده V1 شامل User، Request Manager، Admin، Category، Service، Request، conversation، attachment، Internal Note و history اجرا می‌شود. تعداد و شناسه Request، وضعیت، فایل، مکالمه، یادداشت و تاریخچه پس از migration کنترل می‌شوند.

## چرخه عمر Department

- `DRAFT`: در کاتالوگ requester نمایش داده نمی‌شود و Request جدید نمی‌پذیرد.
- `PUBLISHED`: در صورت active بودن Service Family و Service، Request جدید می‌پذیرد.
- `DISABLED`: Request جدید مسدود است؛ تاریخچه و رسیدگی به Requestهای موجود ادامه دارد.
- `ARCHIVED`: رکورد سازمانی تاریخی و غیرقابل درخواست است؛ Requestهای قبلی قابل مشاهده اما از نظر عملیاتی فقط خواندنی‌اند.

حذف سخت Department در Admin غیرفعال است و FKهای تاریخی از نوع `PROTECT` هستند.

Requestability مؤثر اکنون برابر است با:

`Department=PUBLISHED AND Category.active AND Service.active`

## امنیت و Audit

- lookup و mutationهای عملیاتی از policy و `request_scope` عبور می‌کنند.
- حدس مستقیم URL یا POST مستقیم برای Request اداره دیگر با 404 رد می‌شود.
- Supervisor فقط مشاهده خواندنی دارد و فرم mutation، دانلود attachment و Internal Note را دریافت نمی‌کند.
- Executive Viewer در 2.1A هیچ دسترسی عملیاتی به Request ندارد.
- Internal Note فقط برای Request Manager/Department Lead اداره مالک و Super Admin نمایش داده می‌شود.
- تغییر Department، عضویت و role در Django Admin با `ActivityLog` ثبت می‌شود.
- indexهای Department/status و Department/role برای queryهای scope اضافه شده‌اند.

## سازگاری V1

- URLها، Request IDها، workflow وضعیت، SLA/OLA، مکالمه، فایل، اعلان و فرم‌های پویا حفظ شده‌اند.
- `User.role` در 2.1A حذف نشده است.
- Request Managerهای موجود به Market Development منتقل می‌شوند و مسیر compatibility مانع قفل‌شدن کاربران تازه‌ای می‌شود که هنوز از فرم Legacy ساخته می‌شوند.
- پنل فعلی فقط برچسب Department و حالت read-only لازم را گرفته و بازطراحی عمومی انجام نشده است.

## محدودیت‌ها و نقاط توسعه

### 2.1B

- Department Hub و landing pageهای غنی
- مدیریت Department و Catalogue توسط Department Lead در UI اختصاصی
- تکمیل lifecycle مستقل Service Family فراتر از `active`

### 2.1C

- Enterprise Design System و بازطراحی کامل تجربه کاربری

### 2.2

- Program، Project، Program Manager و Project Manager
- scopeهای Program/Project روی RoleAssignment
- مسیر تأیید Program Manager
- کلید سهمیه آینده باید دقیقاً `Program × Department × Priority × Allocation Period` باشد؛ سهمیه Departmentها مستقل می‌ماند.

### 2.3

- Executive/Department dashboards، BI read model، PDF و گزارش‌ها
- دسترسی جزئی‌تر Supervisor/Executive به داده‌های تحلیلی

### سایر ریسک‌های حفظ‌شده

- Working Calendar و SLA همچنان سراسری‌اند. اتصال Department-specific باید بعداً با FK nullable و fallback به تقویم سراسری افزوده شود تا نتیجه فعلی تغییر نکند.
- `request_data` هنوز snapshot نسخه‌دار schema فرم ندارد.
- مشخصات Service در Request snapshot نشده است؛ فقط Department ارائه‌دهنده اکنون snapshot شده است.
- workflow همچنان در `Request.TRANSITIONS` قرار دارد و approval engine در این release ساخته نشده است.
- PostgreSQL باید در محیط CI/DevOps واقعی هم migration-test شود؛ migrationها فقط از primitiveهای سازگار Django استفاده می‌کنند.
