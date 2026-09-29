from datetime import date, datetime, time, timedelta
from decimal import Decimal
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Attendance, Candidate, Contract, Department, Employee, JobOpening,
    LeaveRequest, LeaveType, Payroll, PayrollPeriod, Position, Transfer, User,
)
from core.services import approve_payroll_period, decide_leave, decide_transfer, generate_payrolls


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu đầy đủ cho FPT HRM (an toàn khi chạy lại)."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Mật khẩu cho toàn bộ tài khoản demo (tối thiểu 8 ký tự).")

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        demo_password = options.get("password") or os.getenv("FPT_HRM_DEMO_PASSWORD")
        if not demo_password or len(demo_password) < 8:
            raise CommandError("Hãy truyền --password hoặc cấu hình FPT_HRM_DEMO_PASSWORD (tối thiểu 8 ký tự).")
        admin, _ = User.objects.get_or_create(username="admin", defaults={"email": "admin@fpt-hrm.local", "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True})
        admin.is_staff = admin.is_superuser = True
        admin.role = User.Role.ADMIN
        admin.set_password(demo_password)
        admin.save()
        hr, _ = User.objects.get_or_create(username="hr", defaults={"email": "hr@fpt-hrm.local", "role": User.Role.HR, "first_name": "Phòng", "last_name": "Nhân sự"})
        hr.role = User.Role.HR
        hr.set_password(demo_password)
        hr.save()

        dept_data = [
            ("BGD", "Ban Giám đốc"), ("NS", "Phòng Nhân sự"), ("CNTT", "Khối Công nghệ"),
            ("KD", "Phòng Kinh doanh"), ("TC", "Phòng Tài chính"),
        ]
        departments = [Department.objects.get_or_create(code=code, defaults={"name": name, "description": f"Đơn vị {name} trong mô hình FPT HRM."})[0] for code, name in dept_data]
        pos_data = [
            ("GD", "Giám đốc", 60000000), ("TP", "Trưởng phòng", 35000000),
            ("CVCC", "Chuyên viên cao cấp", 26000000), ("CV", "Chuyên viên", 18000000),
            ("KSV", "Kỹ sư phần mềm", 24000000), ("TTS", "Thực tập sinh", 7000000),
        ]
        positions = [Position.objects.get_or_create(code=code, defaults={"name": name, "description": name, "reference_salary": salary})[0] for code, name, salary in pos_data]
        first_names = ["Nguyễn Minh", "Trần Thu", "Lê Hoàng", "Phạm Ngọc", "Vũ Anh", "Đỗ Thanh", "Bùi Quang", "Hoàng Mai", "Đặng Đức", "Ngô Khánh", "Dương Hải", "Đinh Thảo", "Lý Tuấn", "Phan Linh", "Trịnh Nam", "Tạ Hà", "Mai Trung", "Lương Vy", "Cao Sơn", "Quách An"]
        last_names = ["Anh", "Hương", "Long", "Lan", "Tuấn", "Hà", "Huy", "Trang", "Thành", "Vy", "Nam", "Linh", "Dũng", "Mai", "Khôi", "Phương", "Kiên", "Ngọc", "Bình", "Thư"]
        employees = []
        for index in range(20):
            email = f"nhanvien{index + 1:02d}@fpt-hrm.local"
            defaults = {
                "full_name": f"{first_names[index]} {last_names[index]}",
                "date_of_birth": date(1985 + index % 14, index % 12 + 1, index % 25 + 1),
                "gender": Employee.Gender.MALE if index % 2 == 0 else Employee.Gender.FEMALE,
                "citizen_id": f"07920{index:07d}", "phone": f"0908{index:06d}",
                "address": f"Quận {index % 10 + 1}, TP. Hồ Chí Minh",
                "hire_date": today - timedelta(days=30 * (index + 1)),
                "department": departments[index % len(departments)], "position": positions[index % len(positions)],
                "base_salary": Decimal(12000000 + index * 850000), "status": Employee.Status.RESIGNED if index == 19 else Employee.Status.ACTIVE,
            }
            employee, _ = Employee.objects.get_or_create(email=email, defaults=defaults)
            employees.append(employee)
            if index < 5:
                username = f"employee{index + 1}"
                user, _ = User.objects.get_or_create(username=username, defaults={"email": email, "role": User.Role.EMPLOYEE})
                user.role = User.Role.EMPLOYEE
                user.is_active = True
                user.set_password(demo_password)
                user.save()
                if employee.user_id != user.id:
                    employee.user = user
                    employee.save(update_fields=["user", "updated_at"])
        for index, dept in enumerate(departments):
            dept.manager = employees[index]
            dept.save(update_fields=["manager", "updated_at"])

        for index, employee in enumerate(employees):
            end = today + timedelta(days=10 + index * 20) if index < 4 else today + timedelta(days=500)
            Contract.objects.get_or_create(contract_number=f"FPT-HĐ-{today.year}-{index + 1:03d}", defaults={"employee": employee, "contract_type": Contract.Type.FIXED, "start_date": employee.hire_date, "end_date": end, "salary": employee.base_salary})

        jobs = []
        for index in range(5):
            job, _ = JobOpening.objects.get_or_create(title=f"{positions[index + 1].name} - Đợt {index + 1}", department=departments[(index + 2) % 5], defaults={"quantity": index + 1, "description": "Tham gia các dự án chuyển đổi số và vận hành doanh nghiệp.", "requirements": "Tư duy chủ động, kỹ năng chuyên môn phù hợp và tinh thần học hỏi.", "start_date": today - timedelta(days=10), "deadline": today + timedelta(days=20 + index * 5), "status": JobOpening.Status.OPEN if index < 4 else JobOpening.Status.CLOSED})
            jobs.append(job)
        candidate_statuses = [Candidate.Status.NEW, Candidate.Status.SCREENED, Candidate.Status.INTERVIEW, Candidate.Status.PASSED, Candidate.Status.FAILED]
        for index in range(15):
            Candidate.objects.get_or_create(email=f"ungvien{index + 1:02d}@example.com", job_opening=jobs[index % 5], defaults={"full_name": f"Ứng viên {index + 1:02d}", "phone": f"0912{index:06d}", "source": ["VietnamWorks", "LinkedIn", "Giới thiệu nội bộ"][index % 3], "notes": "Dữ liệu ứng viên mô phỏng.", "status": candidate_statuses[index % len(candidate_statuses)]})

        for name, paid in [("Nghỉ phép năm", True), ("Nghỉ ốm", True), ("Nghỉ không lương", False), ("Nghỉ thai sản", True), ("Nghỉ công tác", True)]:
            LeaveType.objects.get_or_create(name=name, defaults={"is_paid": paid})
        leave_types = list(LeaveType.objects.all())
        for index in range(5):
            start = today - timedelta(days=25 - index * 3)
            request, created = LeaveRequest.objects.get_or_create(employee=employees[index], start_date=start, defaults={"leave_type": leave_types[index], "end_date": start + timedelta(days=index % 2), "reason": "Nghỉ theo kế hoạch cá nhân.", "status": LeaveRequest.Status.PENDING})
            if created and index < 3:
                decide_leave(request, hr, index != 2, "Lịch công việc chưa phù hợp" if index == 2 else "")

        month_start = today.replace(day=1)
        for employee in employees[:19]:
            for day_num in range(1, today.day + 1):
                work_day = month_start.replace(day=day_num)
                if work_day.weekday() >= 5:
                    continue
                check_in_time = time(8, 20) if (employee.pk + day_num) % 7 == 0 else time(8, 0)
                check_out_time = time(17, 0)
                Attendance.objects.get_or_create(employee=employee, work_date=work_day, defaults={"check_in": check_in_time, "check_out": check_out_time})

        period, _ = PayrollPeriod.objects.get_or_create(month=today.month, year=today.year, defaults={"standard_days": 22})
        if period.status == PayrollPeriod.Status.DRAFT:
            generate_payrolls(period)
            for index, payroll in enumerate(period.payrolls.all()):
                payroll.allowance = Decimal(500000 + (index % 3) * 250000)
                payroll.bonus = Decimal(1000000 if index % 4 == 0 else 0)
                payroll.deduction = Decimal(200000 if index % 6 == 0 else 0)
                payroll.save()
            approve_payroll_period(period, hr)

        transfer_specs = [(employees[7], departments[4], positions[3]), (employees[8], departments[2], positions[4]), (employees[9], departments[1], positions[2])]
        for index, (employee, new_dept, new_pos) in enumerate(transfer_specs):
            transfer, created = Transfer.objects.get_or_create(employee=employee, effective_date=today + timedelta(days=index + 1), defaults={"old_department": employee.department, "old_position": employee.position, "new_department": new_dept, "new_position": new_pos, "reason": "Điều chuyển theo nhu cầu tổ chức."})
            if created and index == 0:
                decide_transfer(transfer, hr, True)
            elif created and index == 1:
                decide_transfer(transfer, hr, False, "Chưa phù hợp kế hoạch nhân sự")

        self.stdout.write(self.style.SUCCESS("Demo data created successfully for FPT HRM."))
        self.stdout.write("Accounts: admin / hr / employee1..employee5 - password supplied by environment/argument")
