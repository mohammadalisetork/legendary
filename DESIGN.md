# Design Context

این سامانه یک محصول سازمانی فارسی و راست‌چین برای ثبت و رسیدگی درخواست خدمت است. Release 2.1B بازطراحی بصری نیست؛ سبک V1 با زمینه روشن، سرمه‌ای سازمانی، آبی عملیاتی، borderهای کم‌رنگ و چگالی متوسط حفظ می‌شود. مرجع اجرایی توکن‌ها و component classها فایل `static/app.css` است.

## اجزای مرجع

- Button: کلاس `btn` با اندازه‌های `btn-sm`، `btn-md` و `btn-lg` و حالت‌های disabled/loading
- Panel/Card: کلاس‌های `panel` و `card`
- Form: فیلد native با ظاهر مشترک؛ native select آگاهانه پذیرفته شده است
- Table: جدول معنایی داخل `table-wrap` با scroll افقی در عرض کم
- Navigation: sidebar موجود، workspace tabs و breadcrumb مشترک `templates/components/breadcrumbs.html`
- Feedback: پیام Django در `flash` و هشدار پایدار در `page-banner`
- Date: Jalali picker موجود؛ ذخیره داخلی تاریخ Gregorian باقی می‌ماند

فرم و صفحه طولانی document scroll دارد و ارتفاع viewport به shell تحمیل نمی‌شود. دکمه اصلی روی desktop متناسب با متن است. Focus ring، markup معنایی، `aria-current`، متن وضعیت و forced-colors baseline حفظ می‌شوند.

فیلد media برای icon/cover Department عمداً اضافه نشده تا migration و سطح حمله آپلود بی‌دلیل زیاد نشود. Design System کامل، typography جدید و polish گسترده مربوط به 2.1C است.
