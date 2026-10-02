"""Server-side Persian RTL PDF with embedded font and application branding."""
from io import BytesIO
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .appearance import DEFAULT_NAME, DEFAULT_PRIMARY
from .models import AppearanceSetting

FONT_PATH=Path(settings.BASE_DIR)/"static"/"fonts"/"DejaVuSans.ttf"


def rtl(value):return get_display(arabic_reshaper.reshape(str(value if value is not None else "نامشخص")))


class Report:
    def __init__(self,output,appearance,title,context):
        if "ReportPersian" not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont("ReportPersian",str(FONT_PATH)))
        self.canvas=canvas.Canvas(output,pagesize=A4,pageCompression=1);self.canvas.setTitle(title)
        self.appearance,self.title,self.context=appearance,title,context
        self.width,self.height=A4;self.left,self.right=42,self.width-42;self.y,self.page=self.height-48,1
        self.primary=HexColor(appearance.primary_color or DEFAULT_PRIMARY);self.font="ReportPersian"

    def space(self,n):
        if self.y-n<62:self.new_page()
        self.y-=n

    def text(self,value,size=9,gap=19,color=None):
        self.space(gap);self.canvas.setFont(self.font,size);self.canvas.setFillColor(color or colors.HexColor('#243447'))
        self.canvas.drawRightString(self.right,self.y,rtl(value))

    def line(self):
        self.space(12);self.canvas.setStrokeColor(colors.HexColor('#d8e1e9'));self.canvas.line(self.left,self.y,self.right,self.y)

    def heading(self,value):
        self.space(27);self.canvas.setFillColor(self.primary);self.canvas.setFont(self.font,13)
        self.canvas.drawRightString(self.right,self.y,rtl(value));self.line()

    def row(self,label,value):
        self.space(22);self.canvas.setFont(self.font,9);self.canvas.setFillColor(colors.HexColor('#657484'))
        self.canvas.drawRightString(self.right,self.y,rtl(label));self.canvas.setFillColor(colors.HexColor('#1d2c3c'))
        self.canvas.drawRightString(self.right-220,self.y,rtl(value))

    def table(self,headers,records,widths=None,max_rows=40):
        widths=widths or [(self.right-self.left-6)/len(headers)]*len(headers)
        if len(widths)!=len(headers):raise ValueError('Invalid PDF table')
        self.space(26);self.canvas.setFillColor(self.primary);self.canvas.rect(self.left,self.y-7,self.right-self.left,24,fill=1,stroke=0)
        x=self.right-8
        for width,header in zip(widths,headers):
            self.canvas.setFont(self.font,8);self.canvas.setFillColor(colors.white);self.canvas.drawRightString(x,self.y,rtl(header));x-=width
        for index,record in enumerate(records[:max_rows]):
            if self.y<85:self.new_page()
            self.space(25);self.canvas.setFillColor(colors.HexColor('#f1f5f8') if index%2==0 else colors.white)
            self.canvas.rect(self.left,self.y-6,self.right-self.left,23,fill=1,stroke=0);x=self.right-8
            for width,value in zip(widths,record):
                self.canvas.setFont(self.font,8);self.canvas.setFillColor(colors.HexColor('#1e3246'))
                display=rtl(value)
                while len(display)>1 and pdfmetrics.stringWidth(display,self.font,8)>width-14:display=display[:-2]+'…'
                self.canvas.drawRightString(x,self.y,display);x-=width
        if len(records)>max_rows:self.text(f'{len(records)-max_rows} ردیف دیگر در خروجی اکسل قابل دریافت است.',size=8)

    def footer(self):
        self.canvas.setStrokeColor(colors.HexColor('#d8e1e9'));self.canvas.line(self.left,45,self.right,45)
        self.canvas.setFillColor(colors.HexColor('#657484'));self.canvas.setFont(self.font,8)
        self.canvas.drawRightString(self.right,30,rtl(self.appearance.app_name or DEFAULT_NAME));self.canvas.drawString(self.left,30,str(self.page))

    def new_page(self):
        self.footer();self.canvas.showPage();self.page+=1;self.y=self.height-48
        self.canvas.setFont(self.font,9);self.canvas.setFillColor(self.primary);self.canvas.drawRightString(self.right,self.y,rtl(self.title));self.y-=25

    def cover(self):
        self.y-=68
        if self.appearance.logo:
            try:
                with self.appearance.logo.open('rb') as source:self.canvas.drawImage(ImageReader(BytesIO(source.read())),self.left,self.y-8,width=54,height=54,preserveAspectRatio=True,mask='auto')
            except (OSError,ValueError):pass
        self.text(self.appearance.app_name or DEFAULT_NAME,size=13,gap=14,color=self.primary)
        self.text(self.title,size=19,gap=67,color=self.primary);self.line()
        from .templatetags.portal_tags import jdate
        window=self.context['window'];self.row('بازه گزارش',f'{jdate(window.start)} تا {jdate(window.end)}');self.row('زمان تولید',jdate(timezone.now()))
        self.row('محدوده دسترسی','داده‌های مجاز دریافت‌کننده')
        labels={'department':'اداره','program':'طرح','project':'پروژه','family':'خانواده','service':'خدمت','status':'وضعیت','priority':'اولویت','requester':'درخواست‌کننده','unit':'واحد','owner':'مسئول'}
        for key,label in labels.items():
            value=self.context['filters'].get(key)
            if value is None:continue
            lookup={'department':self.context['departments'],'program':self.context['programs'],'project':self.context['projects'],'family':self.context['families'],'service':self.context['services']}.get(key)
            if lookup is not None:value=next((str(obj) for obj in lookup if obj.pk==value),str(value))
            self.row(label,value)
        for key in ('snapshot_department','snapshot_program','snapshot_project','snapshot_family','snapshot_service'):
            if key in self.context['filters']:self.row('نام ثبت‌شده در زمان درخواست',self.context['filters'][key])
        self.text('مبنای تعداد درخواست‌ها: تاریخ ثبت نهایی در بازه؛ پیش‌نویس‌ها مستثنا هستند.',size=8,gap=30)


def render_report(context,sections,*,title):
    output=BytesIO();appearance=AppearanceSetting.objects.filter(pk=1).first() or AppearanceSetting()
    report=Report(output,appearance,title,context);report.cover();k=context['kpis']
    for section in ('summary','demand','sla','department','program','service','credit','approval','appendix'):
        if section not in sections:continue
        report.new_page()
        if section=='summary':
            report.heading('خلاصه مدیریتی')
            for label,value in (('کل درخواست‌ها',k['total']),('باز',k['open']),('تکمیل‌شده',k['completed']),('نرخ تکمیل',f"{k['completion_rate']}%" if k['completion_rate'] is not None else 'نامشخص'),('باز خارج از زمان',k['overdue']),('در معرض تأخیر',k['at_risk']),('تغییر خالص صف',k['net_backlog_change'])):report.row(label,value)
            report.text('نرخ تکمیل: تکمیل‌شده تقسیم بر همه درخواست‌های بازه به‌جز رد و لغو.',size=8,gap=30)
        elif section=='demand':
            report.heading('تقاضا و جریان کار');report.row('ورودی بازه',k['new']);report.row('تکمیل در بازه',k['completed_in_period'])
            report.table(['مرحله','تعداد'],[(r['name'],r['total']) for r in context['flow_rows']],[250,250])
            report.heading('ماندگاری درخواست‌های باز');report.table(['روز تقویمی','تعداد'],[(r['name'],r['total']) for r in context['aging_rows']],[250,250])
        elif section=='sla':
            report.heading('عملکرد SLA و زمان')
            for label,value in (('پاسخ اولیه',k['first_sla']),('تکمیل',k['completion_sla'])):report.row(label,f'{value}%' if value is not None else 'داده کافی نیست')
            for label,key in (('میانگین پاسخ اولیه','first_avg'),('میانه پاسخ اولیه','first_median'),('میانگین زمان حل','resolution_avg'),('میانه زمان حل','resolution_median'),('P90 زمان حل (حداقل ۵ نمونه)','resolution_p90'),('زمان عملیاتی ارائه‌دهنده','provider_avg'),('انتظار درخواست‌کننده','requester_wait_avg'),('انتظار طرح','program_wait_avg'),('انتظار مرجع ارشد','senior_wait_avg')):
                value=k[key];report.row(label,f'{round(value/3600,1)} ساعت' if value is not None else 'داده کافی نیست')
            report.text('توقف‌های ثبت‌شده و تأییدهای دارای سیاست توقف SLA از زمان کاری یک بار کسر می‌شوند.',size=8,gap=30)
        elif section in {'department','program','service'}:
            heading,rows={'department':('تحلیل اداره‌ها',context['groups']['department']),'program':('تحلیل طرح‌ها و پروژه‌ها',context['groups']['program']),'service':('تحلیل خانواده و خدمت',context['groups']['service'])}[section]
            report.heading(heading);report.table(['عنوان','تقاضا','باز','تکمیل','خارج از زمان'],[(r['name'],r['total'],r['open'],r['completed'],r['overdue']) for r in rows],[205,75,75,75,70])
            if section in {'program','service'}:
                key='project' if section=='program' else 'family';report.heading('تفکیک '+('پروژه' if key=='project' else 'خانواده خدمت'))
                report.table(['عنوان','درخواست','باز'],[(r['name'],r['total'],r['open']) for r in context['groups'][key]],[280,110,110])
        elif section=='credit':
            report.heading('اولویت و اعتبار');report.table(['طرح','اداره','اولویت','تخصیص','رزرو','مصرف'],[(r['program'],r['department'],r['priority'],r['quantity'],r['reserved'],r['consumed']) for r in context['credits']],[130,115,95,55,55,50])
        elif section=='approval':
            report.heading('تصمیم‌های تأیید');a=context['approvals']
            for label,key in (('کل','total'),('در انتظار','pending'),('تأییدشده','approved'),('ردشده','rejected'),('نرخ تأیید از تصمیم‌های نهایی','rate')):report.row(label,f"{a[key]}%" if key=='rate' and a[key] is not None else a[key])
        elif section=='appendix':
            report.heading('پیوست درخواست‌ها');report.table(['شناسه','اداره','طرح','خدمت','وضعیت'],[(f.request.public_id,f.department,f.program,f.service,f.request.get_status_display()) for f in context['facts']],[105,100,100,110,85],max_rows=100)
    report.footer();report.canvas.save();return output.getvalue()
