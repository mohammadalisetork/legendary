# Release 2.1B: Multi-Department Service Experience

این سند تغییرات شاخه `release/2.1b-multi-department-experience` را ثبت می‌کند. نقطه شروع دقیق شاخه commit ریموت `2f8b1403e69fa74e8891764186dcb7a8cf0e3909` است. این release روی مدل، migration و policy موجود توسعه یافته و 2.1A را بازنویسی نکرده است.

## تجربه Requester

- Department Hub در `/services/` فقط Departmentهای `PUBLISHED` را همراه تعداد خانواده و خدمت فعال نشان می‌دهد.
- landing هر Department در `/services/departments/<code>/` خانواده‌ها و خدمات فعال همان اداره را نمایش می‌دهد و search آن محدود به همان scope است.
- مسیر اطلاعاتی صریح است: `مرکز خدمات ← اداره ← خانواده خدمت ← خدمت ← فرم درخواست`.
- breadcrumb مشترک و Department context در service detail، فرم درخواست، My Requests، request detail و notifications اضافه شده است.
- URL قدیمی `/catalog/` و URL عددی service detail حفظ شده‌اند.
- Service غیرفعال در URL شناخته‌شده صفحه وضعیت روشن و بدون CTA دارد. Department پیش‌نویس برای requester قابل کشف نیست.

## Navigation و Workspace

- Requester فقط مسیرهای عمومی درخواست خود را می‌بیند.
- Request Manager و Department Lead به dashboard و صف عملیاتی دسترسی دارند.
- Department Lead فقط management workspace اداره‌های scope خود را می‌بیند.
- Supervisor صف و dashboard خواندنی دارد و management action دریافت نمی‌کند.
- Super Admin به همه workspaceها و Django Admin دسترسی دارد.

## صف و Dashboard اداره‌ای

پارامتر `department=<code>` به URL صف و dashboard اضافه شده است. مقدار فقط از `authorized_departments()` پذیرفته می‌شود و code اداره دیگر 404 می‌دهد. فیلترهای V1 شامل status، priority، family، service، owner، unit، action-needed، overdue، تاریخ و sort حفظ شده‌اند.

Dashboard شمارش درخواست جدید، در حال بررسی، در حال انجام، نیازمند اطلاعات، overdue و بدون مسئول را برای Department انتخاب‌شده یا کل scope مجاز محاسبه می‌کند.

## مدیریت Department، عضویت و Catalogue

فضای مدیریت application-level شامل فهرست اداره‌ها، ویرایش اطلاعات، اعضا، lifecycle، Service Family و Service است. ساخت Department و Archive فقط برای Super Admin است. Department Lead می‌تواند داده اداره خود را ویرایش، publish/disable و Request Manager همان اداره را اضافه یا غیرفعال کند، ولی نمی‌تواند Department Lead بسازد یا حذف کند.

Lifecycle معتبر:

1. `DRAFT → PUBLISHED` فقط با یک Service Family فعال و یک Service فعال
2. `PUBLISHED → DISABLED | ARCHIVED`
3. `DISABLED → PUBLISHED | ARCHIVED`
4. `ARCHIVED` نهایی

حذف سخت Department اضافه نشده و mutationهای مدیریت در `ActivityLog` ثبت می‌شوند. ایجاد و ویرایش Service Family و Service، active state، زمان‌ها و مسئول پیش‌فرض در workspace انجام می‌شود. queryset مسئول پیش‌فرض فقط مدیران واجدشرایط همان Department است.

فرم‌های پویای `ServiceFormField` همچنان از Django Admin مدیریت می‌شوند؛ انتقال کامل آنها و import اکسل برای 2.4 باقی مانده است. lifecycle مستقل Service Family و media fieldهای icon/cover نیز برای جلوگیری از migration غیرضروری اضافه نشده‌اند.

## امنیت و Query behavior

- policy مرکزی منبع مجوز باقی مانده است.
- `authorized_departments()` فقط discovery workspace را انجام می‌دهد و mutation دوباره `can()` را بررسی می‌کند.
- management خارج از scope با 403 و Request عملیاتی خارج از scope با قرارداد 2.1A و 404 پاسخ می‌دهد.
- Service، Family و owner اداره دیگر در فرم و queryset قابل انتخاب نیستند.
- Hub و landing از annotate، select_related و prefetch استفاده می‌کنند.

## Migration و سازگاری داده

2.1B تغییر schema ندارد و migration جدید ایجاد نمی‌کند. migrationهای 0004 تا 0006 بدون reset یا squash حفظ شده‌اند. درخواست‌های تاریخی، `Request.department` snapshot، RoleAssignmentها، شناسه‌ها، مکالمه، فایل، Internal Note، SLA/OLA و Jalali behavior دست‌نخورده‌اند.

## تست‌ها

۳۹ تست 2.1A پیش از توسعه اجرا و موفق شد. ۹ تست 2.1B اضافه شد که Hub، landing، سازگاری URL، Service غیرفعال، navigation مجوزمحور، scope صف، tamper resistance، جلوگیری از privilege escalation، audit و lifecycle انتشار را پوشش می‌دهد.

## مرز release و roadmap

- 2.1C: Enterprise Design System و polish کامل UI
- 2.2: Program & Project Governance
- 2.3: Priority, Capacity & Approval Engine
- 2.4: Catalogue & Department Scaling، import اکسل و مدیریت کامل form fieldها
- 2.5: Management Intelligence & Reporting، dashboardهای تحلیلی، PDF و read model

کلید quota آینده بدون تغییر باقی می‌ماند: `Program × Department × Priority × Allocation Period`.

هیچ مدل Program، Project، quota، approval، PDF یا analytics در 2.1B پیاده‌سازی نشده است.
