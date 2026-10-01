# UX Contract

## منابع سیاست کسب‌وکار

| حوزه | منبع authoritative |
|---|---|
| مجوز و scope | `portal/policies.py` و `docs/V2_1A_ARCHITECTURE.md` |
| چرخه Department | `Department.Status` و `DepartmentLifecycleForm` |
| چرخه Request | `Request.TRANSITIONS` |
| حفظ داده تاریخی | migrationهای `0004` تا `0006` |

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Django native select | `forms.py` و `static/app.css` | native | keyboard + automated route tests |
| Date | Jalali authored picker | `static/jalali.js` | authored | date tests + manual browser pending |
| Form | Django Forms | `portal/forms.py` | create / edit | validation integration tests |
| Scrollbar | global CSS baseline | `static/app.css` | table horizontal overflow | CSS audit + manual browser pending |
| CRUD | Django views + policy | `portal/views.py` و `portal/policies.py` | redirect after success | full-flow integration tests |

مسیر requester برابر است با «مرکز خدمات ← اداره ← خانواده خدمت ← خدمت ← فرم درخواست». نام فنی `Category` در UI نمایش داده نمی‌شود و URL قدیمی `/catalog/` برای سازگاری باقی می‌ماند. Breadcrumb فقط سلسله‌مراتب واقعی را نشان می‌دهد و آخرین بخش لینک نیست.

اقدام نامرتبط با نقش در navigation مخفی است، ولی backend هر read و mutation را دوباره با policy کنترل می‌کند. دسترسی management خارج از scope با 403 پاسخ می‌گیرد. lookup عملیاتی Request اداره دیگر، مطابق قرارداد امنیتی 2.1A، با 404 رد می‌شود. Supervisor فقط صف و dashboard خواندنی دارد.

Mutationهای مدیریت Department، membership، Service Family و Service به‌صورت pessimistic انجام می‌شوند. موفقیت فقط پس از ذخیره server اعلام می‌شود. حذف سخت Department وجود ندارد؛ membership غیرفعال و Service/Family با active state کنترل می‌شوند.

Transitionهای Department عبارت‌اند از `DRAFT → PUBLISHED`، `PUBLISHED → DISABLED|ARCHIVED` و `DISABLED → PUBLISHED|ARCHIVED`. انتشار حداقل یک خانواده و خدمت فعال می‌خواهد و Archive فقط برای Super Admin است. Service غیرفعال صفحه وضعیت روشن دارد ولی CTA ثبت درخواست ندارد.

فرم‌های جدید `novalidate` دارند و خطاها متن فارسی تولید می‌کنند. Textareaها resize نمی‌شوند. Native select برای 2.1B تصمیم آگاهانه است، چون هندسه popup اختصاصی جزو دامنه این release نیست. کارت‌ها و filter grid در عرض کم تک‌ستونه می‌شوند و جدول‌ها scroll افقی دارند.
