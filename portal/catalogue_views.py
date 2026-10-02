import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .catalogue_import import confirm_batch, export_bytes, template_bytes, validate_workbook
from .forms import RequestBaseForm, ServiceFormFieldForm
from .models import CatalogueImportBatch, Category, Department, Service, ServiceFormField, User
from .policies import Action, can, is_super_admin
from .utils import audit


def _department_access(user, department):
    if not can(user, Action.CATALOGUE_MANAGE, department=department): raise PermissionDenied
    return department


@login_required
def service_fields(request, service_id):
    service=get_object_or_404(Service.objects.select_related("category__department"),pk=service_id)
    _department_access(request.user,service.department)
    fields=service.form_fields.all()
    return render(request,"control/service_fields.html",{"service":service,"fields":fields,"department":service.department})


@login_required
def service_form_preview(request,service_id):
    service=get_object_or_404(Service.objects.select_related("category__department"),pk=service_id)
    _department_access(request.user,service.department)
    form=RequestBaseForm(service=service,user=request.user,allow_incomplete=True)
    return render(request,"control/service_form_preview.html",{"service":service,"form":form,"department":service.department})


@login_required
def service_field_edit(request, service_id, pk=None):
    service=get_object_or_404(Service.objects.select_related("category__department"),pk=service_id)
    _department_access(request.user,service.department)
    obj=get_object_or_404(ServiceFormField,pk=pk,service=service) if pk else None
    form=ServiceFormFieldForm(request.POST or None,instance=obj,service=service)
    if request.method=="POST" and form.is_valid():
        changed=list(form.changed_data); field=form.save()
        audit(request.user,"SERVICE_FORM_FIELD_UPDATED" if obj else "SERVICE_FORM_FIELD_CREATED",field,{"service":service.code,"fields":changed})
        messages.success(request,"فیلد فرم ذخیره شد.");return redirect("service_fields",service_id=service.pk)
    return render(request,"control/object_form.html",{"form":form,"title":"ویرایش فیلد فرم" if obj else "افزودن فیلد فرم","back_url":reverse("service_fields",args=[service.pk]),"department":service.department})


@login_required
@require_POST
def service_field_disable(request,service_id,pk):
    service=get_object_or_404(Service.objects.select_related("category__department"),pk=service_id)
    _department_access(request.user,service.department)
    field=get_object_or_404(ServiceFormField,pk=pk,service=service)
    field.active=False;field.save(update_fields=["active","updated_at"])
    audit(request.user,"SERVICE_FORM_FIELD_DISABLED",field,{"service":service.code})
    messages.success(request,"فیلد غیرفعال شد و از فرم درخواست جدید کنار گذاشته شد.")
    return redirect("service_fields",service_id=service.pk)


@login_required
def import_template(request,department_pk):
    department=_department_access(request.user,get_object_or_404(Department,pk=department_pk))
    response=HttpResponse(template_bytes(),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"]='attachment; filename="service-catalogue-template.xlsx"'
    return response


@login_required
def catalogue_import(request,department_pk):
    department=_department_access(request.user,get_object_or_404(Department,pk=department_pk))
    if request.method=="POST" and request.POST.get("confirm_batch"):
        batch=get_object_or_404(CatalogueImportBatch,pk=request.POST["confirm_batch"],department=department,uploaded_by=request.user,status=CatalogueImportBatch.Status.PREVIEWED)
        if batch.validation_result.get("errors"):
            raise PermissionDenied("فایل دارای خطا است و امکان تأیید ندارد.")
        try:
            created,updated,skipped=confirm_batch(batch,request.user)
        except (ValidationError,Service.DoesNotExist,Category.DoesNotExist,User.DoesNotExist,IntegrityError) as exc:
            batch.status=CatalogueImportBatch.Status.FAILED;batch.validation_result["confirmation_error"]=str(exc);batch.save(update_fields=["status","validation_result"])
            messages.error(request,"ثبت گروهی انجام نشد؛ خطا ثبت شد.");return redirect("catalogue_import",department_pk=department.pk)
        audit(request.user,"CATALOGUE_IMPORT_CONFIRMED",batch,{"created":created,"updated":updated,"skipped":skipped,"sha256":batch.file_sha256})
        messages.success(request,f"ورود انجام شد: {created} ایجاد، {updated} ویرایش، {skipped} ردشده.")
        return redirect("catalogue_import",department_pk=department.pk)
    preview=None
    if request.method=="POST":
        upload=request.FILES.get("file")
        if not upload:
            messages.error(request,"فایل XLSX را انتخاب کنید.")
        else:
            try:
                rows,digest,size=validate_workbook(upload,department)
                errors=sum(len(r["errors"]) for r in rows)
                counts={key:sum(1 for row in rows if row["result"]==key) for key in ("CREATE","UPDATE","SKIP","ERROR")}
                result={"rows":rows,"errors":errors,"counts":counts}
                batch=CatalogueImportBatch.objects.create(department=department,uploaded_by=request.user,original_filename=upload.name[:255],file_size=size,file_sha256=digest,validation_result=result)
                audit(request.user,"CATALOGUE_IMPORT_PREVIEWED",batch,{"rows":len(rows),"errors":errors,"counts":counts,"sha256":digest})
                preview=batch
            except ValidationError as exc:messages.error(request,"فایل قابل پردازش نیست: "+" ".join(exc.messages))
    batches=CatalogueImportBatch.objects.filter(department=department) if is_super_admin(request.user) else CatalogueImportBatch.objects.filter(department=department,uploaded_by=request.user)
    return render(request,"control/catalogue_import.html",{"department":department,"preview":preview,"batches":batches[:20]})


@login_required
def catalogue_export(request):
    requested=request.GET.get("department","")
    services=Service.objects.select_related("category__department","default_owner")
    if is_super_admin(request.user):
        if requested:services=services.filter(category__department__code=requested)
    else:
        from .models import RoleAssignment
        from .policies import department_ids_for_role
        allowed=Department.objects.filter(pk__in=department_ids_for_role(request.user,RoleAssignment.Role.DEPARTMENT_LEAD))
        if requested:
            department=get_object_or_404(allowed,code=requested)
            if not can(request.user,Action.CATALOGUE_MANAGE,department=department):raise PermissionDenied
            services=services.filter(category__department=department)
        else:
            services=services.filter(category__department__in=allowed)
            if not allowed.exists():raise PermissionDenied
    family=request.GET.get("family","")
    if family:services=services.filter(category__slug=family)
    if request.GET.get("active") in {"true","false"}:services=services.filter(active=request.GET["active"]=="true")
    response=HttpResponse(export_bytes(services),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"]='attachment; filename="service-catalogue-export.xlsx"'
    for department in services.values_list("category__department",flat=True).distinct():
        audit(request.user,"CATALOGUE_EXPORTED",Department.objects.get(pk=department),{"family":family,"active":request.GET.get("active","")})
    return response
