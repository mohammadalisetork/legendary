# UX Contract

## منابع رفتار و مجوز

| حوزه | منبع |
|---|---|
| Scope و مجوز | `portal/policies.py` و `docs/V2_1A_ARCHITECTURE.md` |
| چرخهٔ Department | `Department.Status` و `DepartmentLifecycleForm` |
| چرخهٔ Request | `Request.TRANSITIONS` |
| نگهداری دادهٔ تاریخی | migrationهای `0004` تا `0007` |

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Button | `.btn` و کلاس‌های semantic | `static/css/components.css` | primary/secondary/tertiary/danger؛ sm/md/lg | تست ساختار فرم و CSS |
| Select/Listbox | native Django select | `portal/forms.py` و `static/css/forms.css` | native popup | تست فرم و بازبینی مرورگر در محیط DevOps |
| Date | Jalali authored picker | `static/jalali.js` + `static/js/jalali-accessibility.js` | تاریخ اختیاری/الزامی | آزمون تاریخ و بازبینی صفحه |
| Form | Django Forms و request field include | `portal/forms.py`، `templates/components/request_field.html` | ثبت/ویرایش | تست فرم پویا، خطا، CSRF |
| File Upload | FileField و zone مشترک | `portal/forms.py`، `static/js/forms.js` | درخواست/پیام | تست اعتبارسنجی backend و مجوز فایل |
| Table | `<table>` داخل `.table-wrap` | `static/css/tables.css` | صف/فهرست/پیش‌نمایش | تست صفحه‌بندی و حالت خالی |
| Scrollbar | پایهٔ جهانی CSS | `static/css/base.css` | اسکرول افقی جدول | audit CSS و بازبینی مرورگر |
| Toast | Django messages و `.flash` | `templates/base.html`، `static/js/feedback.js` | success/error/warning/info | تست route و markup |
| Breadcrumb | مسیر واقعی داده | `templates/components/breadcrumbs.html` | اداره/خدمت/فرم | تست سلسله‌مراتب |
| Request Journey | inclusion tag | `portal/templatetags/portal_tags.py` و component | requester/management | تست mapping و privacy |
| Confirmation | native `<dialog>` با رفتار app | `static/js/dialogs.js` | بایگانی اداره | تست markup و بازبینی کیبورد |
| CRUD | Django views و policy | `portal/views.py`، `portal/policies.py` | redirect پس از ثبت | تست جریان end-to-end |

## قواعد ثابت

- مسیر درخواست‌دهنده «مرکز خدمات ← اداره ← خانواده خدمت ← خدمت ← فرم درخواست» است. URL قدیمی `/catalog/` برای سازگاری باقی می‌ماند. breadcrumb فقط سلسله‌مراتب واقعی را نشان می‌دهد.
- اقدام نامرتبط با نقش در UI نمایش داده نمی‌شود، اما UI ابزار امنیت نیست؛ backend هر read و mutation را دوباره با policy کنترل می‌کند. خارج از scope مدیریت 403 و lookup درخواست عملیاتی ادارهٔ دیگر مطابق قرارداد 2.1A با 404 رد می‌شود. Supervisor فقط خواندنی است.
- دکمهٔ ثبت نهایی روی دسکتاپ متناسب با متن است. اقدام حیاتی پنهان نیست. انصراف، پیش‌نویس و ثبت نهایی سلسله‌مراتب ثابت دارند. در حالت busy ارسال دوباره مهار می‌شود و نام submitter در POST حفظ می‌شود.
- فرم‌ها `novalidate` دارند و خطا به صورت متن فارسی کنار فیلد یا در پیام پایدار ارائه می‌شود. مقدار واردشده پس از خطا حفظ می‌شود؛ فیلد نامعتبر با `aria-invalid` و تمرکز اولیه مشخص می‌شود. خطای سرور و CSRF هرگز با رنگ تنها نشان داده نمی‌شوند.
- هر جدول حالت خالی مشخص دارد؛ فهرست درخواست‌های کاربر و صف عملیاتی صفحه‌بندی ۲۵تایی دارند. فیلترهای GET در URL می‌مانند. اسکرول افقی به ظرف جدول محدود است.
- اقدام طولانی feedback فوری دارد؛ skeleton فقط پایه‌ای برای بخش‌های async آینده است و تأخیر مصنوعی به navigation اضافه نمی‌شود. از `alert()`، `confirm()` و `prompt()` مرورگر استفاده نشود.
- یادداشت داخلی و رویداد ثبت آن در صفحهٔ درخواست‌دهنده نمایش داده نمی‌شوند. فایل‌ها فقط از endpoint با مجوز Request قابل دریافت هستند.
- تاریخ UI شمسی و ذخیرهٔ داخلی میلادی است. متن، اعداد، جهت آیکون‌ها، اسکرول، تقویم و فرم در RTL باید قابل خواندن بمانند. focus قابل دیدن و `prefers-reduced-motion` الزامی است.
- رنگ و اندازه قلم فقط از مقادیر معتبر `AppearanceSetting` به CSS variable تبدیل می‌شوند؛ رشتهٔ CSS دلخواه از کاربر پذیرفته نمی‌شود. تغییر ظاهر فقط برای Super Admin است.
