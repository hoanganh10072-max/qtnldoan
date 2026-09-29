from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Quản trị viên"
        HR = "HR", "Nhân sự"
        EMPLOYEE = "EMPLOYEE", "Nhân viên"

    role = models.CharField(max_length=12, choices=Role.choices, default=Role.EMPLOYEE)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Department(TimeStampedModel):
    code = models.CharField("Mã phòng ban", max_length=20, unique=True)
    name = models.CharField("Tên phòng ban", max_length=120, unique=True)
    description = models.TextField("Mô tả", blank=True)
    manager = models.ForeignKey("Employee", verbose_name="Trưởng phòng", null=True, blank=True, on_delete=models.SET_NULL, related_name="managed_departments")
    is_active = models.BooleanField("Đang hoạt động", default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def delete(self, *args, **kwargs):
        if self.employees.exists():
            raise ValidationError("Không thể xóa phòng ban đang có nhân viên.")
        return super().delete(*args, **kwargs)


class Position(TimeStampedModel):
    code = models.CharField("Mã chức vụ", max_length=20, unique=True)
    name = models.CharField("Tên chức vụ", max_length=120, unique=True)
    description = models.TextField("Mô tả", blank=True)
    reference_salary = models.DecimalField("Mức lương tham khảo", max_digits=15, decimal_places=0, default=0, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Employee(TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "M", "Nam"
        FEMALE = "F", "Nữ"
        OTHER = "O", "Khác"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Đang làm"
        RESIGNED = "RESIGNED", "Đã nghỉ"

    employee_code = models.CharField("Mã nhân viên", max_length=20, unique=True, blank=True)
    full_name = models.CharField("Họ và tên", max_length=150)
    date_of_birth = models.DateField("Ngày sinh")
    gender = models.CharField("Giới tính", max_length=1, choices=Gender.choices)
    citizen_id = models.CharField("CCCD", max_length=20, unique=True)
    email = models.EmailField("Email", unique=True)
    phone = models.CharField("Số điện thoại", max_length=20)
    address = models.CharField("Địa chỉ", max_length=255)
    hire_date = models.DateField("Ngày vào làm")
    department = models.ForeignKey(Department, verbose_name="Phòng ban", on_delete=models.PROTECT, related_name="employees")
    position = models.ForeignKey(Position, verbose_name="Chức vụ", on_delete=models.PROTECT, related_name="employees")
    base_salary = models.DecimalField("Lương cơ bản", max_digits=15, decimal_places=0, validators=[MinValueValidator(0)])
    avatar = models.ImageField("Ảnh đại diện", upload_to="avatars/%Y/%m/", blank=True, validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])])
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.ACTIVE)
    user = models.OneToOneField(User, verbose_name="Tài khoản", null=True, blank=True, on_delete=models.SET_NULL, related_name="employee")

    class Meta:
        ordering = ["employee_code"]

    def __str__(self):
        return f"{self.employee_code} - {self.full_name}"

    def save(self, *args, **kwargs):
        if not self.employee_code:
            last = Employee.objects.order_by("-id").values_list("id", flat=True).first() or 0
            self.employee_code = f"FPT{last + 1:05d}"
            while Employee.objects.filter(employee_code=self.employee_code).exists():
                last += 1
                self.employee_code = f"FPT{last + 1:05d}"
        super().save(*args, **kwargs)


class Contract(TimeStampedModel):
    class Type(models.TextChoices):
        PROBATION = "PROBATION", "Thử việc"
        FIXED = "FIXED", "Có thời hạn"
        INDEFINITE = "INDEFINITE", "Không xác định thời hạn"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Hiệu lực"
        EXPIRED = "EXPIRED", "Hết hạn"
        TERMINATED = "TERMINATED", "Đã chấm dứt"

    contract_number = models.CharField("Số hợp đồng", max_length=30, unique=True)
    employee = models.ForeignKey(Employee, verbose_name="Nhân viên", on_delete=models.PROTECT, related_name="contracts")
    contract_type = models.CharField("Loại hợp đồng", max_length=15, choices=Type.choices)
    start_date = models.DateField("Ngày bắt đầu")
    end_date = models.DateField("Ngày kết thúc", null=True, blank=True)
    salary = models.DecimalField("Mức lương", max_digits=15, decimal_places=0, validators=[MinValueValidator(0)])
    file = models.FileField("Tệp hợp đồng", upload_to="contracts/%Y/%m/", blank=True, validators=[FileExtensionValidator(["pdf", "doc", "docx"])])
    status = models.CharField("Trạng thái", max_length=15, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-start_date"]

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Ngày kết thúc không được trước ngày bắt đầu."})

    def __str__(self):
        return self.contract_number


class JobOpening(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Đang tuyển"
        CLOSED = "CLOSED", "Đã đóng"

    title = models.CharField("Tên vị trí", max_length=150)
    department = models.ForeignKey(Department, verbose_name="Phòng ban", on_delete=models.PROTECT, related_name="job_openings")
    quantity = models.PositiveIntegerField("Số lượng", default=1)
    description = models.TextField("Mô tả công việc")
    requirements = models.TextField("Yêu cầu")
    start_date = models.DateField("Ngày bắt đầu")
    deadline = models.DateField("Hạn tuyển")
    status = models.CharField("Trạng thái", max_length=10, choices=Status.choices, default=Status.OPEN)

    def clean(self):
        if self.deadline and self.start_date and self.deadline < self.start_date:
            raise ValidationError({"deadline": "Hạn tuyển không được trước ngày bắt đầu."})

    def __str__(self):
        return self.title


class Candidate(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "NEW", "Mới tiếp nhận"
        SCREENED = "SCREENED", "Đã sàng lọc"
        INTERVIEW = "INTERVIEW", "Đang phỏng vấn"
        PASSED = "PASSED", "Đạt yêu cầu"
        FAILED = "FAILED", "Không đạt"
        HIRED = "HIRED", "Đã nhận việc"

    full_name = models.CharField("Họ tên", max_length=150)
    email = models.EmailField("Email", unique=True)
    phone = models.CharField("Số điện thoại", max_length=20)
    job_opening = models.ForeignKey(JobOpening, verbose_name="Vị trí ứng tuyển", on_delete=models.PROTECT, related_name="candidates")
    cv = models.FileField("CV", upload_to="cvs/%Y/%m/", blank=True, validators=[FileExtensionValidator(["pdf", "doc", "docx"])])
    source = models.CharField("Nguồn ứng viên", max_length=100, blank=True)
    notes = models.TextField("Ghi chú / kết quả phỏng vấn", blank=True)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.NEW)
    converted_employee = models.OneToOneField(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_candidate")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name


class Attendance(TimeStampedModel):
    class Status(models.TextChoices):
        WORKING = "WORKING", "Đang làm"
        ON_TIME = "ON_TIME", "Đúng giờ"
        LATE = "LATE", "Đi muộn"
        HALF_DAY = "HALF_DAY", "Nửa ngày"

    employee = models.ForeignKey(Employee, verbose_name="Nhân viên", on_delete=models.PROTECT, related_name="attendances")
    work_date = models.DateField("Ngày làm việc", default=timezone.localdate)
    check_in = models.TimeField("Giờ vào", null=True, blank=True)
    check_out = models.TimeField("Giờ ra", null=True, blank=True)
    hours_worked = models.DecimalField("Số giờ làm", max_digits=5, decimal_places=2, default=0)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.WORKING)
    note = models.CharField("Ghi chú", max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["employee", "work_date"], name="unique_attendance_per_day")]
        ordering = ["-work_date", "employee__employee_code"]

    def clean(self):
        if self.check_out and not self.check_in:
            raise ValidationError({"check_out": "Phải chấm công vào trước khi chấm công ra."})
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValidationError({"check_out": "Giờ ra phải sau giờ vào."})

    def calculate(self):
        if not self.check_in:
            self.hours_worked = Decimal("0")
            self.status = self.Status.WORKING
        elif not self.check_out:
            self.status = self.Status.WORKING
        else:
            start = datetime.combine(self.work_date, self.check_in)
            end = datetime.combine(self.work_date, self.check_out)
            seconds = Decimal(str((end - start).total_seconds()))
            # Ca 08:00-17:00 có một giờ nghỉ trưa, tương ứng 8 giờ công chuẩn.
            if self.check_in <= time(12, 0) and self.check_out >= time(13, 0):
                seconds -= Decimal("3600")
            self.hours_worked = (seconds / Decimal("3600")).quantize(Decimal("0.01"))
            if self.hours_worked < 4:
                self.status = self.Status.HALF_DAY
            elif self.check_in > time(8, 15):
                self.status = self.Status.LATE
            else:
                self.status = self.Status.ON_TIME

    def save(self, *args, **kwargs):
        self.full_clean()
        self.calculate()
        super().save(*args, **kwargs)


class LeaveType(TimeStampedModel):
    name = models.CharField("Loại nghỉ", max_length=100, unique=True)
    is_paid = models.BooleanField("Được hưởng lương", default=True)

    def __str__(self):
        return self.name


class LeaveRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ duyệt"
        APPROVED = "APPROVED", "Đã duyệt"
        REJECTED = "REJECTED", "Từ chối"
        CANCELLED = "CANCELLED", "Đã hủy"

    employee = models.ForeignKey(Employee, verbose_name="Nhân viên", on_delete=models.PROTECT, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, verbose_name="Loại nghỉ", on_delete=models.PROTECT)
    start_date = models.DateField("Ngày bắt đầu")
    end_date = models.DateField("Ngày kết thúc")
    days = models.PositiveIntegerField("Số ngày", default=1)
    reason = models.TextField("Lý do")
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.PENDING)
    approver = models.ForeignKey(User, verbose_name="Người duyệt", null=True, blank=True, on_delete=models.SET_NULL)
    rejection_reason = models.TextField("Lý do từ chối", blank=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Ngày kết thúc không được trước ngày bắt đầu."})
        if self.employee_id and self.start_date and self.end_date:
            overlap = LeaveRequest.objects.filter(employee_id=self.employee_id).exclude(pk=self.pk).exclude(status__in=[self.Status.REJECTED, self.Status.CANCELLED]).filter(start_date__lte=self.end_date, end_date__gte=self.start_date)
            if overlap.exists():
                raise ValidationError("Khoảng thời gian nghỉ bị trùng với đơn đã có.")
        if self.status == self.Status.REJECTED and not self.rejection_reason.strip():
            raise ValidationError({"rejection_reason": "Bắt buộc nhập lý do từ chối."})

    def save(self, *args, **kwargs):
        if self.start_date and self.end_date:
            self.days = (self.end_date - self.start_date).days + 1
        self.full_clean()
        super().save(*args, **kwargs)


class PayrollPeriod(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bản nháp"
        APPROVED = "APPROVED", "Đã duyệt"
        PAID = "PAID", "Đã thanh toán"

    month = models.PositiveSmallIntegerField("Tháng")
    year = models.PositiveSmallIntegerField("Năm")
    standard_days = models.DecimalField("Ngày công chuẩn", max_digits=5, decimal_places=2, default=22, validators=[MinValueValidator(1)])
    status = models.CharField("Trạng thái", max_length=10, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["month", "year"], name="unique_payroll_period"),
            models.CheckConstraint(condition=Q(month__gte=1, month__lte=12), name="valid_payroll_month"),
        ]
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"Tháng {self.month:02d}/{self.year}"


class Payroll(TimeStampedModel):
    period = models.ForeignKey(PayrollPeriod, verbose_name="Kỳ lương", on_delete=models.PROTECT, related_name="payrolls")
    employee = models.ForeignKey(Employee, verbose_name="Nhân viên", on_delete=models.PROTECT, related_name="payrolls")
    base_salary = models.DecimalField("Lương cơ bản", max_digits=15, decimal_places=0)
    standard_days = models.DecimalField("Ngày công chuẩn", max_digits=5, decimal_places=2)
    actual_days = models.DecimalField("Ngày công thực tế", max_digits=5, decimal_places=2, default=0)
    allowance = models.DecimalField("Phụ cấp", max_digits=15, decimal_places=0, default=0)
    bonus = models.DecimalField("Thưởng", max_digits=15, decimal_places=0, default=0)
    overtime_pay = models.DecimalField("Tiền làm thêm", max_digits=15, decimal_places=0, default=0)
    deduction = models.DecimalField("Khấu trừ", max_digits=15, decimal_places=0, default=0)
    net_salary = models.DecimalField("Lương thực nhận", max_digits=15, decimal_places=0, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["period", "employee"], name="unique_employee_payroll")]
        ordering = ["employee__employee_code"]

    @property
    def is_locked(self):
        return self.period.status != PayrollPeriod.Status.DRAFT

    def calculate_net(self):
        standard_days = Decimal(str(self.standard_days or 0))
        if not standard_days:
            return Decimal("0")
        base_salary = Decimal(str(self.base_salary or 0))
        actual_days = Decimal(str(self.actual_days or 0))
        allowance = Decimal(str(self.allowance or 0))
        bonus = Decimal(str(self.bonus or 0))
        overtime_pay = Decimal(str(self.overtime_pay or 0))
        deduction = Decimal(str(self.deduction or 0))
        value = base_salary / standard_days * actual_days + allowance + bonus + overtime_pay - deduction
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        if self.pk:
            original = Payroll.objects.select_related("period").get(pk=self.pk)
            if original.period.status != PayrollPeriod.Status.DRAFT:
                raise ValidationError("Bảng lương đã khóa, không thể chỉnh sửa.")
        self.net_salary = self.calculate_net()
        super().save(*args, **kwargs)


class Transfer(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ duyệt"
        APPROVED = "APPROVED", "Đã duyệt"
        REJECTED = "REJECTED", "Từ chối"

    employee = models.ForeignKey(Employee, verbose_name="Nhân viên", on_delete=models.PROTECT, related_name="transfers")
    old_department = models.ForeignKey(Department, verbose_name="Phòng ban cũ", on_delete=models.PROTECT, related_name="transfers_from")
    new_department = models.ForeignKey(Department, verbose_name="Phòng ban mới", on_delete=models.PROTECT, related_name="transfers_to")
    old_position = models.ForeignKey(Position, verbose_name="Chức vụ cũ", on_delete=models.PROTECT, related_name="transfers_from")
    new_position = models.ForeignKey(Position, verbose_name="Chức vụ mới", on_delete=models.PROTECT, related_name="transfers_to")
    effective_date = models.DateField("Ngày hiệu lực")
    reason = models.TextField("Lý do")
    approver = models.ForeignKey(User, verbose_name="Người phê duyệt", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField("Lý do từ chối", blank=True)

    class Meta:
        ordering = ["-effective_date"]

    def __str__(self):
        return f"{self.employee} → {self.new_department}"
