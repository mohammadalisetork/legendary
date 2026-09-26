import json, re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from portal.models import Category, Service, ServiceFormField, WorkingCalendar

DEFAULT_FIELDS=[
 ("problem","مسئله و چرایی درخواست","textarea",True,"مسئله‌ای را که باید حل شود شرح دهید."),
 ("decision","این خروجی برای چه تصمیمی لازم است؟","textarea",True,""),
 ("deliverable","خروجی مورد انتظار","textarea",True,""),
 ("audience","مخاطب خروجی","text",True,""),
 ("evidence","اطلاعات و مستندات موجود","textarea",False,""),
 ("constraints","محدودیت‌ها و وابستگی‌های شناخته‌شده","textarea",False,""),
]
PERSIAN={"۰":"0","۱":"1","۲":"2","۳":"3","۴":"4","۵":"5","۶":"6","۷":"7","۸":"8","۹":"9"}
def nums(value):
    value="".join(PERSIAN.get(c,c) for c in value or ""); return [int(x) for x in re.findall(r"\d+",value)]
def delivery_range(value):
    normalized="".join(PERSIAN.get(c,c) for c in value or "")
    c1=re.search(r"C1\s*:\s*(\d+)\s*تا\s*(\d+)",normalized,re.I)
    if c1:return int(c1.group(1)),int(c1.group(2))
    pair=re.search(r"(\d+)\s*تا\s*(\d+)",normalized)
    if pair:return int(pair.group(1)),int(pair.group(2))
    values=nums(normalized)
    return (values[0],values[0]) if values else (5,10)
class Command(BaseCommand):
    help="Seed catalogue from the supplied source HTML without overwriting edited records"
    @transaction.atomic
    def handle(self,*args,**opts):
        html=(Path(__file__).resolve().parents[3]/"data/source-catalog.html").read_text(encoding="utf-8")
        match=re.search(r'<script id="seed" type="application/json">([\s\S]*?)</script>',html)
        if not match: raise RuntimeError("Catalogue seed was not found")
        rows=json.loads(match.group(1)); families=[]
        for row in rows:
            if row["family"] not in families: families.append(row["family"])
        categories={}
        for order,name in enumerate(families):
            categories[name],_=Category.objects.get_or_create(name=name,defaults={"slug":f"category-{order+1}","description":f"خدمات خانواده {name}","display_order":order})
        created=0
        for order,row in enumerate(rows):
            response=nums(row.get("response")); min_days,max_days=delivery_range(row.get("sla"))
            service,is_new=Service.objects.get_or_create(code=row["code"],defaults={"name":row["name"],"category":categories[row["family"]],"domain":row["domain"],"short_description":row["when"],"full_description":row["definition"],"purpose":row["when"],"scope":row["definition"],"deliverables":row["output"],"required_inputs":row["input"],"request_requirements":row["input"],"process_information":"ثبت بریف، بررسی کامل بودن ورودی، توافق دامنه و زمان، اجرا، بازبینی و پذیرش.","excluded":row["excluded"],"service_role":row["role"],"acceptance_criteria":row["accept"],"legacy_sla":row["sla"],"initial_response_days":max(1,max(response) if response else 2),"delivery_min_days":min_days,"delivery_max_days":max(max_days,min_days),"display_order":order})
            if is_new:
                created+=1
                for i,(key,label,kind,required,help_text) in enumerate(DEFAULT_FIELDS): ServiceFormField.objects.create(service=service,key=key,label=label,field_type=kind,required=required,help_text=help_text,display_order=i)
        WorkingCalendar.objects.get_or_create(name="تقویم کاری اصلی",defaults={"weekend_days":[4]})
        self.stdout.write(self.style.SUCCESS(f"Catalogue ready: {len(rows)} services, {created} created"))
