# FPT HRM — Hệ thống quản lý nhân sự mô phỏng

FPT HRM là website nguyên khối phục vụ đồ án học phần Quản trị hệ thống nhân lực. Hệ thống mô phỏng các quy trình nhân sự của Công ty Cổ phần FPT cho mục đích học tập; **đây không phải hệ thống nội bộ chính thức của FPT**.

## Công nghệ

- Python 3.12+ (đã kiểm thử với Python 3.14)
- Django 5.2 LTS, Django Template và Django Authentication
- Bootstrap 5, Chart.js, HTML/CSS/JavaScript thuần
- SQLite, Django ORM và migrations
- CSV có BOM UTF-8 để mở đúng tiếng Việt trong Excel

## Chức năng đã hoàn thành

- Đăng nhập, đăng xuất, đổi mật khẩu, khóa tài khoản; phân quyền backend `ADMIN`, `HR`, `EMPLOYEE`; trang 403/404.
- Phòng ban và chức vụ: danh sách, tìm kiếm, phân trang, thêm, xem, sửa, xóa có bảo vệ quan hệ; xem nhân viên theo phòng ban/chức vụ.
- Hồ sơ nhân viên: mã tự động, ảnh đại diện, lọc/tìm kiếm, chi tiết, cập nhật, nghỉ việc/khóa tài khoản, lịch sử hợp đồng, CSV.
- Hợp đồng: thêm/sửa, tệp đính kèm, validation thời hạn, lịch sử theo nhân viên, cảnh báo hết hạn 30 ngày.
- Tuyển dụng: vị trí tuyển dụng, ứng viên, CV, lọc/tìm kiếm, kết quả phỏng vấn, tiếp nhận ứng viên đạt yêu cầu thành nhân viên và tài khoản trong transaction.
- Chấm công: vào/ra, chống trùng ngày, kiểm tra thứ tự giờ, tự tính giờ và trạng thái, HR điều chỉnh, lọc và CSV.
- Nghỉ phép: tạo/hủy, chống trùng thời gian, duyệt/từ chối một lần, bắt buộc lý do từ chối; phép hưởng lương được cộng vào ngày công kỳ lương.
- Tiền lương: kỳ lương duy nhất theo tháng/năm, tự lấy ngày công, sinh lương toàn bộ nhân sự đang làm, điều chỉnh phụ cấp/thưởng/làm thêm/khấu trừ, duyệt và khóa, đánh dấu thanh toán, phiếu lương cá nhân, CSV.
- Thuyên chuyển: đề nghị, duyệt/từ chối trong transaction, chỉ cập nhật hồ sơ sau duyệt, giữ đầy đủ thông tin cũ/mới.
- Dashboard quản trị với 8 chỉ số và biểu đồ theo phòng ban, giới tính, trạng thái, biến động, chi phí lương; dashboard cá nhân không lộ dữ liệu người khác.
- Trung tâm báo cáo và CSV cho nhân viên, hợp đồng, tuyển dụng, chấm công, nghỉ phép, bảng lương và thuyên chuyển.
- Management command sinh dữ liệu demo idempotent; 20 automated tests cho quyền và nghiệp vụ trọng yếu.

## Cấu trúc thư mục

```text
fpt_hrm/
├── core/
│   ├── management/commands/seed_demo.py
│   ├── migrations/
│   ├── admin.py, decorators.py, forms.py
│   ├── models.py, services.py, urls.py, views.py
│   └── tests.py
├── fpt_hrm/              # settings, URL gốc, WSGI
├── static/               # CSS và JavaScript
├── templates/            # layout, trang nghiệp vụ, lỗi 403/404
├── media/                # file upload (được gitignore)
├── .env.example
├── IMPLEMENTATION_CHECKLIST.md
├── manage.py
└── requirements.txt
```

## Cài đặt

### Windows PowerShell

```powershell
cd D:\BTW\fpt_hrm
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Nếu máy dùng `uv`:

```powershell
uv venv
uv pip install -r requirements.txt
```

Sửa `.env` trước khi chạy. Dùng secret ngẫu nhiên và mật khẩu demo chỉ dành cho môi trường học tập:

```env
DJANGO_SECRET_KEY=mot-chuoi-bi-mat-dai-ngau-nhien
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
FPT_HRM_DEMO_PASSWORD=Demo@123
```

Không đưa `.env`, database hoặc file upload thật vào Git.

### Migration và dữ liệu mẫu

```powershell
python manage.py migrate
python manage.py seed_demo --password "Demo@123"
```

Lệnh seed an toàn khi chạy lại. Có thể bỏ `--password` nếu đã đặt `FPT_HRM_DEMO_PASSWORD` trong `.env`.

### Chạy server

```powershell
python manage.py runserver
```

Mở [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Tài khoản demo

Database bàn giao đã seed với mật khẩu `Demo@123`:

| Vai trò | Tên đăng nhập | Mật khẩu |
|---|---|---|
| ADMIN | `admin` | `Demo@123` |
| HR | `hr` | `Demo@123` |
| EMPLOYEE | `employee1` … `employee5` | `Demo@123` |

Đổi mật khẩu ngay nếu dùng ngoài buổi trình diễn. Mật khẩu không nằm trong source ứng dụng; command nhận từ đối số hoặc biến môi trường rồi lưu hash bằng Django.

## Vai trò và quyền hạn

- **ADMIN:** toàn quyền nghiệp vụ, tài khoản/phân quyền, danh mục và báo cáo; có quyền vào Django Admin tại `/django-admin/`.
- **HR:** quản lý hồ sơ, hợp đồng, tuyển dụng, công/phép, lương, thuyên chuyển và báo cáo; không quản lý tài khoản hệ thống.
- **EMPLOYEE:** chỉ xem hồ sơ, công, đơn nghỉ và phiếu lương của chính mình; chấm công vào/ra, gửi/hủy đơn đang chờ và đổi mật khẩu.

Mọi quyền được kiểm tra tại view/backend. Việc ẩn menu chỉ hỗ trợ trải nghiệm, không phải cơ chế bảo mật.

## Quy tắc nghiệp vụ và giả định

- Múi giờ `Asia/Ho_Chi_Minh`; ngày hiển thị `dd/mm/yyyy`; tiền hiển thị VND.
- Ca chuẩn 08:00–17:00 gồm một giờ nghỉ trưa, tức 8 giờ công. Sau 08:15 là đi muộn. Có làm nhưng dưới 4 giờ được tính 0,5 ngày; từ 4 giờ trở lên tính 1 ngày.
- Mỗi nhân viên chỉ có một bản ghi công/ngày. Không thể ra trước khi vào hoặc có giờ ra trước giờ vào.
- Phép đã duyệt và có hưởng lương được cộng vào ngày công, tối đa bằng ngày công chuẩn.
- Nhân viên có dữ liệu phát sinh không có chức năng xóa vật lý; thao tác nghỉ việc chuyển trạng thái và khóa tài khoản.
- Email ứng viên là duy nhất để tránh tiếp nhận cùng một người nhiều lần.
- Bootstrap và Chart.js được nạp qua CDN; nghiệp vụ server vẫn hoạt động nếu CDN tạm thời không khả dụng nhưng biểu đồ/giao diện Bootstrap cần kết nối mạng trình duyệt.

## Công thức lương mô phỏng

```text
Lương thực nhận =
    Lương cơ bản / Ngày công chuẩn × Ngày công thực tế
    + Phụ cấp + Thưởng + Tiền làm thêm - Khấu trừ
```

Hệ thống cố ý không tính thuế thu nhập cá nhân và bảo hiểm thực tế.

## Kiểm thử

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test -v 2
```

Kết quả bàn giao: **20/20 test vượt qua**, `manage.py check` không có lỗi. Test bao phủ chuyển hướng đăng nhập, phân quyền nhân viên, riêng tư phiếu lương, mã/email nhân viên, bảo vệ phòng ban, chấm công, nghỉ phép, công thức/khóa lương, thuyên chuyển và smoke test toàn bộ trang chính.

## Luồng demo đề xuất

1. Đăng nhập `admin`; xem dashboard, tạo phòng ban/chức vụ và kiểm tra tài khoản.
2. Đăng nhập `hr`; tạo vị trí tuyển dụng, thêm ứng viên, chuyển trạng thái sang “Đạt yêu cầu”, rồi “Tiếp nhận” để tạo nhân viên/tài khoản.
3. Đăng nhập `employee1`; chấm công vào/ra, gửi đơn nghỉ và xem dữ liệu cá nhân.
4. Đăng nhập `hr`; duyệt đơn nghỉ, tạo kỳ lương mới, sinh bảng lương, điều chỉnh và duyệt khóa.
5. Đăng nhập nhân viên; mở phiếu lương cá nhân.
6. Đăng nhập `hr`; tạo và duyệt thuyên chuyển, quan sát hồ sơ được cập nhật.
7. Đăng nhập `admin`; xem biểu đồ/báo cáo và tải các tệp CSV.

## Chức năng chưa làm và giới hạn

Các mục P0 và P1 trong đề bài đã được triển khai. Theo phạm vi loại trừ/P2, phiên bản này chưa có PDF, email, quên mật khẩu qua email, audit log đầy đủ, máy chấm công/GPS/nhận diện khuôn mặt, API tách rời, thuế/bảo hiểm thực tế và tích hợp bên ngoài.

## Hướng phát triển

- Lưu file trên object storage và quét MIME/virus trong môi trường thật.
- Audit log bất biến cho các thao tác duyệt và thay đổi lương.
- Lịch làm việc/ngày lễ để tính công chính xác hơn qua nhiều tháng.
- Xuất PDF có chữ ký, email thông báo, backup và triển khai PostgreSQL.
- Bổ sung CSP, HTTPS bắt buộc, rate limiting và quản lý secret chuyên dụng khi production.
