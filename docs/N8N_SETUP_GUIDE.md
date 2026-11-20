# Hướng dẫn n8n: Vercel end-to-end

Workflow bàn giao: `n8n/EUCERIN_Vercel_EndToEnd.json`; workflow lỗi: `n8n/EUCERIN_Vercel_Error_Handler.json`. Cả hai để `active: false`, không chứa credential, và workflow chính dùng production host đã xác minh.

## Cài đặt

1. Import hai JSON vào cùng một n8n workspace.
2. Tạo Header Auth credential: tên header `X-API-Key`, giá trị là cùng `ML_API_KEY` đã đặt trong Vercel. Chọn credential này ở các HTTP Request node. Không dán key vào Code node, JSON export hay tài liệu.
3. Mở `02 | Config - Vercel, Drive, Telegram`; điền `sourceFileId`, `outputFolderId`, và `telegramChatId`. `apiBaseUrl` đã là `https://eucerin-ml-automation.vercel.app`; giữ HTTPS và không thêm dấu `/` cuối.
4. Gắn Google Drive OAuth credential cho node metadata/download/upload và chọn thư mục đầu ra có quyền ghi.
5. Tạo Telegram credential bằng bot token do chủ bot cung cấp; chọn credential ở cả node báo cáo và Error Handler. Không đưa bot token vào JSON.
6. Trong Settings của workflow chính, chọn `EUCERIN | Vercel Error Handler` làm Error Workflow. Error handler chỉ gửi workflow, node và execution ID đã làm sạch; không chuyển stack trace, body CSV hoặc credential.
7. Chạy Manual Trigger. Kiểm tra metadata/CSV, 8 file `run_id__<filename>` ở thư mục Drive và trạng thái run trên API. Sau khi Drive upload được API acknowledge đầy đủ, workflow mới reserve và gửi Telegram; API đánh dấu delivered sau khi nhận message ID.
8. Chỉ sau một lần chạy thủ công thành công mới bật workflow. Schedule đặt 09:00 theo timezone `Asia/Ho_Chi_Minh`.

## Vòng đời và retry

API giữ trạng thái bền vững trong Postgres; khóa duy nhất dựa trên SHA-256 CSV + model version. Nếu cùng dữ liệu/model được gửi lại, run đang chờ được tiếp tục thay vì tạo run mới; run đã delivered không gửi lại.

Các HTTP Request có retry giới hạn và timeout 120 giây. Telegram không bật auto-retry để tránh gửi tin lặp khi kết quả request không rõ. API reserve thông báo trước khi gửi; nếu Telegram đã nhận nhưng n8n mất phản hồi, trạng thái `notification_reserved` cần được người vận hành đối soát thủ công trước khi xử lý tiếp. Không đánh dấu complete bằng một message ID giả.

Workflow là template đã kiểm tra JSON và Code node bằng test cục bộ; do credential và tài khoản n8n chưa được cung cấp trong repo, chưa xác nhận import/chạy thật trên instance của bạn.
