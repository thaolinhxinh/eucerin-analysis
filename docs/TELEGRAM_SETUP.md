# Cấu hình Telegram

1. Tạo hoặc chọn bot Telegram và lấy token qua quy trình bảo mật của Telegram. Không gửi token vào Git, workflow export, chat nhóm hoặc tài liệu.
2. Trong n8n tạo Telegram API credential và gắn vào node `16 | Telegram: Send summary` cùng node `E3 | Telegram: Error alert` trong Error Handler.
3. Điền `telegramChatId` trong config node của hai workflow. Chỉ sử dụng chat mà chủ dự án cho phép; không có tin thử nào được gửi trong quá trình kiểm thử hiện tại.
4. Chạy một lần sau khi Drive upload và acknowledge hoàn tất. API reservation đảm bảo một run chỉ phát một lần; API `/complete` lưu message ID sau khi Telegram trả thành công.

Nếu gửi tin bị lỗi hoặc timeout, run có thể ở trạng thái `notification_reserved`. Không retry gửi bằng tay ngay lập tức vì Telegram có thể đã nhận tin; kiểm tra chat trước, rồi đối soát run. Error Handler cần được chọn trong workflow Settings và credential Telegram của nó cũng phải được gắn riêng.

Tin báo gồm ngày chốt, khoảng dự báo, model version, số SKU/SKU–ngày, tổng xác suất kỳ vọng, phân bố ADI/CV², cảnh báo rà soát và giới hạn diễn giải. Tổng xác suất là số SKU–ngày kỳ vọng có phát sinh bán theo log, không phải Units Sold, GMV hay khuyến nghị nhập hàng.
