# HƯỚNG DẪN TRIỂN KHAI EUCERIN ML AUTOMATION

> Phiên bản bàn giao: 18/11/2026. Trạng thái: kiểm thử Python API cục bộ đạt; **Google Drive, n8n và Telegram thật chưa được kết nối / kiểm thử từ môi trường bàn giao**.

## 1. Luồng xử lý

1. **Manual Trigger / Schedule Trigger** (9:00 mỗi ngày, múi giờ Asia/Ho_Chi_Minh).
2. Google Drive **Get metadata**: lấy `id`, `md5Checksum` hoặc `modifiedTime` / `version` của file CSV lịch sử.
3. API `POST /check-source`: bỏ qua nếu cùng nguồn, cùng revision và cùng phiên bản mô hình đã **gửi Telegram thành công** trước đó.
4. Google Drive **Download** đưa file vào binary field `data`.
5. API `POST /predict-file`: đọc dữ liệu đủ lịch sử, kiểm tra thiếu cột, khóa trùng và ngày thiếu; chạy Random Forest Classifier từ artefact Chương 6; tính phân nhóm ADI/CV².
6. API trả danh sách CSV **chưa upload**; n8n tải từng CSV qua `GET /results/...` và tải lên một thư mục Drive riêng. Sau mỗi tệp, n8n thông báo `POST /runs/.../ack-file` để lưu ID tệp đã tạo.
7. Khi đã ghi nhận đủ 8 CSV, API `POST /runs/.../reserve-notification` khóa quyền gửi Telegram cho đúng một lần gửi tự động.
8. Telegram `sendMessage` gửi bản tóm tắt; nếu thành công, n8n gọi `POST /runs/.../complete` để ghi trạng thái `delivered`.
9. Nếu một bước thất bại, Error Workflow riêng có thể báo về Telegram; dữ liệu lỗi chi tiết không gửi ra ngoài.

**Giới hạn đúng thực tế:** đây là quy trình vận hành trên CSV nguồn đã được cập nhật trong Google Drive, **không phải kết nối trực tiếp với TikTok Shop hoặc FastMoss**. Power BI đọc file CSV đã được tải lên Drive. Việc tự động refresh dataset/semantic model Power BI Service cần cấu hình riêng phù hợp giấy phép và nguồn dữ liệu.

## 2. Khởi chạy FastAPI trên máy cá nhân

Yêu cầu Python 3.13 và gói trong `requirements.txt`; mô hình joblib này được tạo với scikit-learn 1.8.0, không nên tùy tiện hạ phiên bản. Trong thư mục giải nén:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# Tạo biến môi trường ML_API_KEY thành khóa dài ngẫu nhiên, tuyệt đối không dùng placeholder.
# PowerShell: $env:ML_API_KEY="KHOA_CUA_BAN"
# Linux/macOS: export ML_API_KEY="KHOA_CUA_BAN"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Kiểm tra `http://127.0.0.1:8000/health`. Máy chủ trên localhost **không thể được n8n Cloud gọi từ internet**. Để kết nối n8n Cloud, triển khai API bằng Docker/FastAPI lên dịch vụ công khai có HTTPS hoặc sử dụng một reverse proxy bảo mật. Không mở API trực tiếp qua HTTP không mã hóa. Cần lưu bền vững thư mục `storage` (SQLite + kết quả).

### Docker

```bash
cp .env.example .env
# Sửa .env: ML_API_KEY=<secret có độ dài cao>; APP_MODE=research / production
# Không đưa .env lên GitHub
docker compose up --build -d
```

Compose mặc định ánh xạ `127.0.0.1:8000`, không phải URL công khai. Cần HTTPS reverse proxy + kiểm tra khả năng truy cập từ n8n. Trên nền tảng đám mây, cấu hình persistent volume cho `/app/storage` và dùng một Uvicorn worker (SQLite + lock tiến trình); không chạy đa worker song song nếu chưa thay cơ sở dữ liệu tập trung. Kiểm tra yêu cầu dung lượng sau vài tháng lưu output.

## 3. Thiết lập Google Drive

1. Tạo một file **CSV thuần UTF-8**, không phải Google Sheet. Dùng `reference/historical_eucerin_confirmed.csv` để demo, không sửa tên cột `dt`, `product_id`, `units_sold`, `title`, `is_eucerin`.
2. Tạo thư mục `EUCERIN_ML_RESULTS` riêng trong Google Drive.
3. Copy ID file nguồn và ID folder kết quả từ URL Drive. Không phải API key.
4. Trong n8n, tạo **Google Drive OAuth2 credential** có quyền đọc file nguồn và tạo file trong thư mục kết quả.
5. Với **node 02** (Get metadata) và **node 05** (Download), sửa `PASTE_SOURCE_FILE_ID` thành ID thật.
6. Với **node 11** (Upload CSV), sửa `PASTE_OUTPUT_FOLDER_ID` thành ID folder thật, chọn My Drive/Shared Drive phù hợp.
7. Kiểm tra output node 02 có `id` và ít nhất một trong `md5Checksum`, `modifiedTime`, `version`; nếu không có, chỉnh Return Fields hoặc chọn Get File (metadata) để trả đầy đủ. Không dùng revision mặc định vì có thể bỏ sót thay đổi.
8. Không chọn file Google Sheets xuất CSV nếu có thể giữ file CSV gốc: Google Drive `md5Checksum` thường dành cho file binary, revision metadata có thể khác với Google Sheets.

## 4. Cấu hình n8n sau khi import

- Import `n8n/EUCERIN_n8n_Complete.json` bằng **Workflow → ⋯ → Import from File**.
- Import `n8n/EUCERIN_n8n_Error_Handler.json` vào workflow riêng.
- Gán **Google Drive OAuth2** cho 3 node: 02 metadata, 05 download, 11 upload.
- Tạo n8n credential **Header Auth**: header tên **`X-API-Key`** và value chính là `ML_API_KEY` máy chủ FastAPI (không đặt key vào JSON). Gán credential này cho **toàn bộ HTTP Request nodes** 03, 06, 10, 12, 14, 17.
- Tại các node HTTP Request, thay **`https://YOUR-HTTPS-ML-API.example`** bằng URL HTTPS thật (bảo toàn biểu thức sau phần domain ở URL động).
- Tạo **Telegram API credential** bằng token BotFather, gán cho node 16 và E3; thay `PASTE_TELEGRAM_CHAT_ID` bằng Chat ID nhóm hoặc chat riêng nhận báo cáo.
- Trong workflow chính vào **Settings → Error Workflow**, chọn `EUCERIN | Error Handler → Telegram`; bật/activate Error Workflow và main workflow sau khi chạy thử thành công.
- Kiểm tra timezone workflow đặt `Asia/Ho_Chi_Minh` và lịch 09:00. Tắt Schedule trước khi cấu hình xong tránh gửi thông báo ngoài ý muốn.
- **Đặc biệt:** node 11 Upload CSV và node 16 Telegram **không bật Retry On Fail** nhằm giảm rủi ro tạo duplicate khi dịch vụ ngoài nhận thành công nhưng n8n mất kết nối trước khi nhận response. Với các node `GET/check/ack` có thể retry giới hạn.

## 5. Chế độ nghiên cứu và chế độ dữ liệu mới

**Research Mode (mặc định):** `APP_MODE=research`. Chỉ dùng dữ liệu kết thúc **12/10/2026** để tái lập kết quả nghiên cứu. Dự báo hồi cứu **13–19/10/2026**; đây không phải dự báo tính từ hiện tại.

**Production Mode:** đặt `APP_MODE=production`, nguồn CSV chứa toàn bộ lịch sử tích lũy đến ngày mới nhất. Dự báo luôn là 7 ngày sau ngày chốt thực tế. Dữ liệu của **toàn bộ SKU có trong mô hình đã huấn luyện** phải có bản ghi mỗi ngày từ đầu kỳ; không tự gán 0 cho ngày thiếu. SKU mới được đếm và cảnh báo ngoài phạm vi, **không có xác suất dự báo** trước khi huấn luyện lại. Cảnh báo drift được đưa vào Telegram và output nhưng không tự retrain. Nếu mô hình đã già so với dữ liệu mới, phải đánh giá out-of-time trước khi sử dụng để ra quyết định.

## 6. Chống trùng và khôi phục sau lỗi

API lưu bảng `runs` và `uploads` bằng SQLite trong volume. Khóa run là **SHA-256 dữ liệu nguồn + phiên bản mô hình**. Từng CSV được xác nhận bằng tên và Drive File ID. Chạy lại file hoàn toàn giống sau khi đã gửi tin nhắn thành công sẽ bỏ qua.

- Nếu lỗi ở phần tải lên Drive **trước khi API nhận ack-file**, tệp Drive có thể đã được tạo dù n8n không nhận response. Cần kiểm tra tên deterministic `RUN_ID__FILENAME` trong thư mục Drive trước khi chạy lại để tránh tệp trùng. Nếu đã tạo nhưng chưa ack, có thể thủ công gọi `ack-file` với ID thật từ Drive rồi chạy lại.
- Sau `reserve-notification`, API cấm gửi tự động lần hai. Nếu Telegram bị lỗi hoặc đã gửi thành công nhưng `/complete` thất bại, run dừng ở `notification_reserved`. Người quản trị phải đối chiếu tin nhắn thật trong Telegram và trạng thái API. **Không tự gửi lại** để tránh gửi trùng.
- Nếu `status=delivered`, không chạy lại cùng dữ liệu/mô hình. Trường `Model_Run_History.csv` được chụp tại thời điểm export trước gửi Telegram, trạng thái cuối cùng phải xem **`GET /history`** trên API, không suy luận `delivered` từ bản snapshot.
- API không bảo đảm exactly-once phân tán tuyệt đối giữa Google Drive và Telegram; cơ chế hiện tại ưu tiên không gửi trùng tự động hơn là luôn tự động thử lại gửi khi phản hồi thất lạc.

## 7. Tài liệu tham khảo cấu hình

- n8n Google Drive File operations: https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.googledrive/file-operations/
- n8n Error handling: https://docs.n8n.io/flow-logic/error-handling/
- n8n HTTP Request: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/
- FastAPI: https://fastapi.tiangolo.com/
