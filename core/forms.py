from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .models import (
    Attendance, Candidate, Contract, Department, Employee, JobOpening,
    LeaveRequest, Payroll, PayrollPeriod, Position, Transfer, User,
)


class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)
            if isinstance(field.widget, forms.DateInput):
                field.widget.attrs["type"] = "date"
            if isinstance(field.widget, forms.TimeInput):
                field.widget.attrs["type"] = "time"


class LoginForm(BootstrapMixin, AuthenticationForm):
    username = forms.CharField(label="Tên đăng nhập")
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput)


class DepartmentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ["code", "name", "description", "manager", "is_active"]


class PositionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Position
        fields = ["code", "name", "description", "reference_salary"]


class EmployeeForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["full_name", "date_of_birth", "gender", "citizen_id", "email", "phone", "address", "hire_date", "department", "position", "base_salary", "avatar", "status", "user"]
        widgets = {"date_of_birth": forms.DateInput(), "hire_date": forms.DateInput()}

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class ContractForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Contract
        fields = ["contract_number", "employee", "contract_type", "start_date", "end_date", "salary", "file", "status"]
        widgets = {"start_date": forms.DateInput(), "end_date": forms.DateInput()}


class JobOpeningForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = JobOpening
        fields = ["title", "department", "quantity", "description", "requirements", "start_date", "deadline", "status"]
        widgets = {"start_date": forms.DateInput(), "deadline": forms.DateInput()}


class CandidateForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ["full_name", "email", "phone", "job_opening", "cv", "source", "notes", "status"]


class CandidateConversionForm(BootstrapMixin, forms.Form):
    date_of_birth = forms.DateField(label="Ngày sinh", widget=forms.DateInput())
    gender = forms.ChoiceField(label="Giới tính", choices=Employee.Gender.choices)
    citizen_id = forms.CharField(label="CCCD", max_length=20)
    address = forms.CharField(label="Địa chỉ", max_length=255)
    hire_date = forms.DateField(label="Ngày vào làm", widget=forms.DateInput())
    position = forms.ModelChoiceField(label="Chức vụ", queryset=Position.objects.all())
    base_salary = forms.DecimalField(label="Lương cơ bản", min_value=0, decimal_places=0)
    username = forms.CharField(label="Tên đăng nhập", max_length=150)
    password = forms.CharField(label="Mật khẩu ban đầu", min_length=8, widget=forms.PasswordInput)

    def clean_username(self):
        value = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username=value).exists():
            raise ValidationError("Tên đăng nhập đã tồn tại.")
        return value


class AttendanceForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ["employee", "work_date", "check_in", "check_out", "note"]
        widgets = {"work_date": forms.DateInput(), "check_in": forms.TimeInput(), "check_out": forms.TimeInput()}


class LeaveRequestForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "reason"]
        widgets = {"start_date": forms.DateInput(), "end_date": forms.DateInput()}


class RejectForm(BootstrapMixin, forms.Form):
    reason = forms.CharField(label="Lý do từ chối", widget=forms.Textarea(attrs={"rows": 3}))


class PayrollPeriodForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PayrollPeriod
        fields = ["month", "year", "standard_days"]


class PayrollAdjustmentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Payroll
        fields = ["actual_days", "allowance", "bonus", "overtime_pay", "deduction"]

    def clean(self):
        data = super().clean()
        if self.instance.pk and self.instance.is_locked:
            raise ValidationError("Bảng lương đã khóa, không thể chỉnh sửa.")
        return data


class TransferForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Transfer
        fields = ["employee", "new_department", "new_position", "effective_date", "reason"]
        widgets = {"effective_date": forms.DateInput()}


class UserForm(BootstrapMixin, forms.ModelForm):
    password = forms.CharField(label="Mật khẩu", required=False, min_length=8, widget=forms.PasswordInput, help_text="Bỏ trống khi chỉnh sửa để giữ mật khẩu hiện tại.")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "is_active", "password"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["password"].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
