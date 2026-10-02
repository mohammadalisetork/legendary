# Release 2.1C: Enterprise Design System

این release روی commit `c99292de8c9a6060967e0490e658f645c7e9ef38` از شاخهٔ 2.1B ساخته شده است. Django، قالب‌های server-rendered، URLها، policy، درخواست‌ها، SLA/OLA و تاریخچهٔ migration حفظ شده‌اند. نسخهٔ در حال اجرای سازمان در دسترس این پروژه نیست؛ این سند فقط GitHub baseline و بررسی محلی را توصیف می‌کند.

## اصول و معماری CSS

محیط استفاده یک سامانهٔ عملیاتی فارسی است: اطلاعات در جدول‌ها متراکم اما خوانا، فرم‌ها روشن، و اقدام اصلی متناسب با محتوا است. بخش خدمات برای کشف خدمت فضای بیشتری دارد و صف رسیدگی فشرده‌تر است. آیکون خطی صرفاً کنار متن می‌آید. سایه برای سطح برجسته یا پنجرهٔ تأیید استفاده می‌شود.

`static/app.css` ورودی اصلی است. ترتیب بارگذاری: `legacy.css` برای سازگاری V1/2.1B، سپس `tokens.css`، `base.css`، `layout.css`، `components.css`، `forms.css`، `tables.css` و `pages.css`. قواعد تازه در ماژول مربوطه نوشته می‌شوند؛ `legacy.css` مالک تصمیم جدید نیست. `DESIGN.md` جهت و مقادیر پیش‌فرض را مستند می‌کند، `tokens.css` مالک اجرایی توکن‌ها است، و `AppearanceSetting` فقط چند متغیر برند را در ریشهٔ سند تغییر می‌دهد.

| گروه | نمونهٔ توکن و کاربرد |
|---|---|
| رنگ | `--primary` برای اقدام و انتخاب، `--accent` برای تأکید محدود، `--surface`، `--background`، `--border` و رنگ‌های معنایی success/warning/danger/info |
| متن | متن پایه `1rem` از ۱۵ پیکسل؛ عنوان‌ها `--font-h1/h2/h3`؛ `--line-body:1.75` |
| فاصله | `--space-1/2/3/4/6/8/12/16` به ترتیب ۴، ۸، ۱۲، ۱۶، ۲۴، ۳۲، ۴۸، ۶۴ پیکسل |
| شکل | radius کوچک ۵، متوسط ۸ و بزرگ ۱۲ پیکسل |
| عمق | surface، raised، overlay؛ بدون سایهٔ سنگین دائمی |
| حرکت | fast ۱۲۰، normal ۱۸۰، slow ۲۸۰ میلی‌ثانیه؛ reduced-motion همهٔ حرکت‌های غیرضروری را حذف می‌کند |
| تمرکز | focus-visible مشترک با ring رنگ اصلی؛ forced-colors قابل استفاده می‌ماند |

قلم اختصاصی در مخزن نیست. stack پیش‌فرض Tahoma، Segoe UI و Arial است؛ انتخاب‌های `system`، `tahoma` و `arial` فقط stackهای مجاز هستند. متن فارسی و انگلیسی و اعداد در یک سلسله‌مراتب rem-based قرار می‌گیرند. بستهٔ فونت خارجی یا CDN اضافه نشده است. بارگذاری WOFF2/WOFF عمداً در این release پیاده‌سازی نشده؛ فرایند بررسی مجوز، بهداشت فایل و سرو امن آن باید در release جدا تکمیل شود. فیلد `font_family` و متغیر `--brand-font` نقطهٔ اتصال آماده‌اند.

## اجزا و رفتار

| جزء | مالک |
|---|---|
| Button، Card، Metric Card، Badge، Status Badge، Empty State، Skeleton، Toast، Dialog | `static/css/components.css` و قالب‌های مربوط |
| Input، Textarea، Select، Checkbox، Radio، File Upload و Filter Bar | Django Forms، `static/css/forms.css` و `static/js/forms.js` |
| Jalali Date Picker | `static/jalali.js` و لایهٔ دسترسی `static/js/jalali-accessibility.js` |
| Table و Pagination | `static/css/tables.css`، `<table>` معنایی، صفحه‌بندی سمت سرور |
| Breadcrumb | `templates/components/breadcrumbs.html` |
| Page Header، Tabs، Avatar و Navigation Item | پوستهٔ `templates/base.html` و `static/css/layout.css` |
| Conversation و Request Journey | `templates/components/conversation.html`، `request_journey.html` و tag مشترک |

فرم درخواست بر اساس زمینهٔ اداره/خانواده/خدمت، اطلاعات پایه و جزئیات پویا گروه‌بندی می‌شود. انصراف tertiary، پیش‌نویس secondary و ثبت نهایی primary است. فایل‌های انتخاب‌شده نام و حجم دارند، با همان input استاندارد قابل انتخاب‌اند و پیش از ارسال می‌توان انتخاب را حذف کرد؛ پیشرفت درصدی آپلود برای POST معمولی ادعا نمی‌شود. خطاهای server معتبرند و JavaScript فقط بازخورد زودهنگام می‌دهد.

جدول‌های عملیاتی sticky header داخل ظرف اسکرول افقی، hover سطر، برچسب وضعیت با متن و حالت خالی دارند. فیلترهای GET در URL باقی می‌مانند. درخواست‌های کاربر و صف اداره در هر صفحه ۲۵ ردیف دارند. جست‌وجوی سمت سرور debounce ندارد. اسکلت بارگذاری به صورت پایهٔ CSS موجود است و روی navigation معمولی تأخیر ساختگی ایجاد نمی‌کند.

در Request Journey، پنج مرحلهٔ «ثبت درخواست، بررسی، پذیرش، اجرا، تکمیل» از وضعیت‌های موجود نگاشت می‌شوند. پذیرش همان `ACCEPTED` است و موتور approval آینده نیست. رویدادهای واقعی RequestHistory در زیر آن نمایش داده می‌شوند. رویداد یادداشت داخلی در نمای requester فیلتر می‌شود و متن آن فقط با policy backend در نمای مجاز قابل مشاهده است. فیلتر Approvals نمایش داده نمی‌شود، چون هنوز وجود ندارد.

## تنظیم ظاهر و ذخیره‌سازی

`AppearanceSetting` یک ردیف با کلید ۱ دارد و بدون seed، پیش‌فرض‌ها را ارائه می‌کند. فقط Super Admin می‌تواند `/appearance/` را تغییر دهد. فیلدها: نام سامانه، رنگ اصلی، رنگ تأکیدی، اندازهٔ پایه ۱۴ تا ۱۸، قلم از سه گزینهٔ مجاز و لوگوی PNG حداکثر یک مگابایت. رنگ‌ها فقط hex شش‌رقمی با کنتراست حداقل 4.5:1 نسبت به متن سفید هستند؛ hover/active از همان رنگ مشتق می‌شود. فایل PNG با ساختار chunk، CRC و ابعاد ۱۶ تا ۲۰۴۸ پیکسل اعتبارسنجی می‌شود و با `Content-Type: image/png` از route عمومی لوگو ارائه می‌گردد تا در login هم دیده شود. مسیر فایل با UUID ساخته می‌شود و به storage پیش‌فرض local/S3 موجود متکی است. از SVG و CSS دلخواه پشتیبانی نمی‌شود. Reset تنظیمات فعال را به پیش‌فرض برمی‌گرداند؛ فایل لوگوی قبلی از storage پاک نمی‌شود و چرخهٔ پاک‌سازی orphan به تیم زیرساخت سپرده می‌شود.

## RTL، دسترسی و responsive

سند `lang=fa` و `dir=rtl` دارد. مسیرها، فرم‌ها، جدول‌ها و timeline راست‌چین‌اند. آیتم‌های ناوبری active با متن پررنگ، زمینه و خط مشخص می‌شوند. کنترل‌ها label، focus-visible و نقش معنایی دارند. دیالوگ بایگانی با `<dialog>`، تمرکز اولیه روی انصراف، Escape و بازگشت تمرکز کار می‌کند. تقویم شمسی برچسب دکمه‌ها و حرکت کلیدهای جهت را دریافت کرده است. در عرض ۷۸۰ پیکسل ناوبری افقی، فرم تک‌ستونه و جدول دارای اسکرول افقی است. بازبینی تعاملی در مرورگر محلی در محیط Agent موجود نبود؛ نتیجهٔ بصری و keyboard E2E باید در محیط دارای مرورگر دوباره بررسی شود.

## مهاجرت و توسعهٔ بعدی

Migration `0007_appearancesetting` فقط جدول تنظیم ظاهر را اضافه می‌کند؛ schema و دادهٔ درخواست و Department تغییر نمی‌کنند. تازه‌نصب و ارتقای دیتابیس پرشده باید با migration و آزمون حفظ داده تأیید شوند. مسیر roadmap: 2.2 حکمرانی Program/Project، 2.3 Priority/Capacity/Approval، 2.4 مقیاس‌دهی کاتالوگ و Department، 2.5 هوش مدیریتی و گزارش. برای 2.3، سهمیه دقیقاً بر اساس `Program × Department × Priority × Allocation Period` مستقل می‌ماند.
