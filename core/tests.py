from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Attendance, Department, Employee, LeaveRequest, LeaveType, Payroll,
    PayrollPeriod, Position, Transfer, User,
)
from .services import approve_payroll_period, decide_leave, decide_transfer


class BaseDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(code="IT", name="Công nghệ")
        cls.department2 = Department.objects.create(code="HR", name="Nhân sự")
        cls.position = Position.objects.create(code="DEV", name="Kỹ sư", reference_salary=20000000)
        cls.position2 = Position.objects.create(code="LEAD", name="Trưởng nhóm", reference_salary=30000000)
        cls.admin = User.objects.create_superuser("admin", "admin@test.local", "Demo@123")
        cls.hr = User.objects.create_user("hr", "hr@test.local", "Demo@123", role=User.Role.HR)
        cls.user1 = User.objects.create_user("employee1", "e1@test.local", "Demo@123", role=User.Role.EMPLOYEE)
        cls.user2 = User.objects.create_user("employee2", "e2@test.local", "Demo@123", role=User.Role.EMPLOYEE)
        cls.employee1 = Employee.objects.create(
            full_name="Nguyễn Văn Một", date_of_birth=date(1995, 1, 1), gender=Employee.Gender.MALE,
            citizen_id="001095000001", email="e1@test.local", phone="0901000001", address="Hà Nội",
            hire_date=date(2024, 1, 1), department=cls.department, position=cls.position,
            base_salary=Decimal("22000000"), user=cls.user1,
        )
        cls.employee2 = Employee.objects.create(
            full_name="Trần Thị Hai", date_of_birth=date(1996, 2, 2), gender=Employee.Gender.FEMALE,
            citizen_id="001096000002", email="e2@test.local", phone="0901000002", address="TP.HCM",
            hire_date=date(2024, 2, 1), department=cls.department, position=cls.position,
            base_salary=Decimal("18000000"), user=cls.user2,
        )


class PermissionTests(BaseDataMixin, TestCase):
    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("employee_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_employee_cannot_access_employee_admin(self):
        self.client.force_login(self.user1)
        self.assertEqual(self.client.get(reverse("employee_list")).status_code, 403)

    def test_employee_cannot_view_another_payslip(self):
        period = PayrollPeriod.objects.create(month=1, year=2026, standard_days=22, status=PayrollPeriod.Status.APPROVED)
        payroll = Payroll.objects.create(period=period, employee=self.employee2, base_salary=18000000, standard_days=22, actual_days=22)
        self.client.force_login(self.user1)
        self.assertEqual(self.client.get(reverse("payslip", args=[payroll.pk])).status_code, 403)

    def test_employee_can_view_own_profile(self):
        self.client.force_login(self.user1)
        self.assertEqual(self.client.get(reverse("employee_detail", args=[self.employee1.pk])).status_code, 200)


class EmployeeRulesTests(BaseDataMixin, TestCase):
    def test_employee_code_is_automatic_and_unique(self):
        self.assertTrue(self.employee1.employee_code.startswith("FPT"))
        self.assertNotEqual(self.employee1.employee_code, self.employee2.employee_code)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Employee.objects.create(
                    employee_code=self.employee1.employee_code, full_name="Trùng mã", date_of_birth=date(1990, 1, 1),
                    gender=Employee.Gender.MALE, citizen_id="999999999999", email="other@test.local", phone="0909",
                    address="Test", hire_date=date.today(), department=self.department, position=self.position, base_salary=1,
                )

    def test_employee_email_is_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Employee.objects.create(
                    full_name="Trùng email", date_of_birth=date(1990, 1, 1), gender=Employee.Gender.MALE,
                    citizen_id="888888888888", email=self.employee1.email, phone="0909", address="Test",
                    hire_date=date.today(), department=self.department, position=self.position, base_salary=1,
                )

    def test_department_with_employees_cannot_be_deleted(self):
        with self.assertRaises(ValidationError):
            self.department.delete()


class AttendanceRulesTests(BaseDataMixin, TestCase):
    def test_one_attendance_per_employee_per_day(self):
        Attendance.objects.create(employee=self.employee1, work_date=date(2026, 1, 2), check_in=time(8), check_out=time(17))
        with self.assertRaises(ValidationError):
            Attendance.objects.create(employee=self.employee1, work_date=date(2026, 1, 2), check_in=time(8, 5))

    def test_cannot_check_out_before_check_in(self):
        with self.assertRaises(ValidationError):
            Attendance.objects.create(employee=self.employee1, work_date=date(2026, 1, 3), check_out=time(17))

    def test_hours_are_calculated_correctly(self):
        item = Attendance.objects.create(employee=self.employee1, work_date=date(2026, 1, 4), check_in=time(8), check_out=time(17))
        self.assertEqual(item.hours_worked, Decimal("8.00"))
        self.assertEqual(item.status, Attendance.Status.ON_TIME)


class LeaveRulesTests(BaseDataMixin, TestCase):
    def setUp(self):
        self.leave_type = LeaveType.objects.create(name="Nghỉ phép năm")

    def test_end_date_cannot_precede_start_date(self):
        with self.assertRaises(ValidationError):
            LeaveRequest.objects.create(employee=self.employee1, leave_type=self.leave_type, start_date=date(2026, 2, 2), end_date=date(2026, 2, 1), reason="Test")

    def test_overlapping_leave_is_rejected(self):
        LeaveRequest.objects.create(employee=self.employee1, leave_type=self.leave_type, start_date=date(2026, 2, 2), end_date=date(2026, 2, 4), reason="Test")
        with self.assertRaises(ValidationError):
            LeaveRequest.objects.create(employee=self.employee1, leave_type=self.leave_type, start_date=date(2026, 2, 3), end_date=date(2026, 2, 5), reason="Trùng")

    def test_processed_leave_cannot_be_approved_again(self):
        item = LeaveRequest.objects.create(employee=self.employee1, leave_type=self.leave_type, start_date=date(2026, 3, 2), end_date=date(2026, 3, 2), reason="Test")
        decide_leave(item, self.hr, True)
        with self.assertRaises(ValidationError):
            decide_leave(item, self.hr, True)


class PayrollRulesTests(BaseDataMixin, TestCase):
    def test_duplicate_payroll_is_rejected(self):
        period = PayrollPeriod.objects.create(month=4, year=2026)
        Payroll.objects.create(period=period, employee=self.employee1, base_salary=22000000, standard_days=22, actual_days=20)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payroll.objects.create(period=period, employee=self.employee1, base_salary=22000000, standard_days=22, actual_days=21)

    def test_salary_formula(self):
        period = PayrollPeriod.objects.create(month=5, year=2026)
        payroll = Payroll.objects.create(period=period, employee=self.employee1, base_salary=22000000, standard_days=22, actual_days=20, allowance=1000000, bonus=500000, overtime_pay=300000, deduction=200000)
        self.assertEqual(payroll.net_salary, Decimal("21600000"))

    def test_approved_payroll_is_locked(self):
        period = PayrollPeriod.objects.create(month=6, year=2026)
        payroll = Payroll.objects.create(period=period, employee=self.employee1, base_salary=22000000, standard_days=22, actual_days=22)
        approve_payroll_period(period, self.hr)
        payroll.allowance = 100
        with self.assertRaises(ValidationError):
            payroll.save()


class TransferRulesTests(BaseDataMixin, TestCase):
    def test_profile_changes_only_after_approval_and_history_is_kept(self):
        item = Transfer.objects.create(
            employee=self.employee1, old_department=self.department, new_department=self.department2,
            old_position=self.position, new_position=self.position2, effective_date=date(2026, 7, 1), reason="Điều động",
        )
        self.employee1.refresh_from_db()
        self.assertEqual(self.employee1.department, self.department)
        decide_transfer(item, self.hr, True)
        self.employee1.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(self.employee1.department, self.department2)
        self.assertEqual(item.old_department, self.department)
        self.assertEqual(item.new_position, self.position2)
        with self.assertRaises(ValidationError):
            decide_transfer(item, self.hr, True)


class SmokeViewTests(BaseDataMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_main_pages_render_without_server_error(self):
        urls = [
            reverse("dashboard"), reverse("department_list"), reverse("department_create"),
            reverse("position_list"), reverse("employee_list"), reverse("employee_create"),
            reverse("contract_list"), reverse("job_list"), reverse("candidate_list"),
            reverse("attendance_list"), reverse("leave_list"), reverse("payroll_period_list"),
            reverse("transfer_list"), reverse("reports"), reverse("user_list"),
            reverse("department_detail", args=[self.department.pk]),
            reverse("employee_detail", args=[self.employee1.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_employee_personal_pages_render(self):
        self.client.force_login(self.user1)
        for url in [reverse("dashboard"), reverse("attendance_list"), reverse("leave_list"), reverse("leave_create"), reverse("my_payslips")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_login_page_renders(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
