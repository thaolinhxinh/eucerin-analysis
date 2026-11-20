# Google Drive input/output

## Chuẩn bị file nguồn

Đặt CSV nguồn trong Drive và dùng file ID ổn định trong config node n8n. Đây phải là CSV được export, không phải Google Sheet. Bắt buộc có các cột `product_id`, `dt`, `units_sold`, `title`, `is_eucerin`; `gmv` là tùy chọn. Ngày theo `YYYY-MM-DD`; SKU–ngày không được trùng; Units Sold phải là số nguyên không âm.

API dùng dữ liệu lịch sử cộng dồn. Cần giữ ngày bắt đầu của tập train và chuỗi quan sát liên tục cho các SKU đã huấn luyện; API không tự điền ngày thiếu thành 0. SKU mới được ghi nhận là chưa được model hỗ trợ, không tự retrain. Không đổi kiểu Google Sheet thành CSV bằng cách sửa đuôi file.

## Credential và thư mục

Trong n8n tạo Google Drive OAuth credential bằng tài khoản được phép đọc file nguồn và tạo file trong thư mục đầu ra. Dán source file ID và output folder ID vào config Code node. Không cấp quyền public cho dữ liệu.

Kết quả được lưu với tên `RUN_ID__FactOccurrenceForecast_PowerBI.csv`, v.v.; các lần chạy giữ lịch sử và không cố ý ghi đè. Sau từng upload, n8n gọi endpoint acknowledge. API chỉ cho phép reserve Telegram sau khi đủ cả 8 file được xác nhận.

## Cần người vận hành xác nhận

Credential Drive chưa được kết nối ở repo này. Hãy chạy workflow thủ công và kiểm tra file trong đúng thư mục trước khi bật lịch. Nếu upload thành công nhưng node acknowledge lỗi, chạy lại cùng nguồn để tiếp tục run; không xóa ledger hoặc giả lập acknowledgement.
