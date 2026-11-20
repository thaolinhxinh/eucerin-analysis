# Checklist triển khai & minh chứng đồ án Chương 7

- [ ] Colab: mở notebook, upload dữ liệu, chạy Runtime → Run all.
- [ ] Colab: kết quả validation / holdout / artifact được tạo từ dữ liệu thật.
- [ ] GitHub: repository private có Dockerfile, render.yaml, app, models, reference.
- [ ] Render: Blueprint chọn plan có persistent disk và thiết lập ML_API_KEY.
- [ ] Render: /health trả 200; không chứa secret trong log/response.
- [ ] Render: /check-source yêu cầu Header Auth hợp lệ.
- [ ] Google Drive: file CSV source đúng cột, Google OAuth cho n8n đủ quyền.
- [ ] n8n: import workflow, cập nhật Config, gán 3 loại credentials.
- [ ] n8n: chạy Manual thành công, không có lỗi API/Drive.
- [ ] Google Drive: có đủ 8 CSV theo RunID mới.
- [ ] Telegram: bot đã gửi thông tin run ID, dự báo 7 ngày và cảnh báo (không phải khuyến nghị nhập hàng).
- [ ] n8n: chạy lại cùng CSV & model không gửi Telegram lặp.
- [ ] Power BI: import CSV theo RunID, kiểm tra ngày và xác suất 0–1.
- [ ] n8n: gắn workflow lỗi, test lỗi cố ý bằng ID Drive không đúng.
- [ ] n8n: sau khi ổn định mới Active lịch chạy hàng ngày.
- [ ] Báo cáo Chương 7: chụp ảnh source, workflow nodes, Render health/log, Drive output, Telegram, Power BI, bảng kiểm thử.

**Trạng thái trước triển khai:** Chỉ các bước kiểm thử local có thể được xác minh, còn các bước dịch vụ cloud phải chạy trên tài khoản người dùng.
