# PHỤ LỤC CHƯƠNG 6 – ML A + C VÀ TỰ ĐỘNG HÓA ĐẦU RA

## 1. Nguồn và phạm vi

Tập dữ liệu Eucerin đã xác nhận từ FastMoss có 8.030 bản ghi SKU–ngày của 94 SKU. Theo tiêu chí chỉ giữ SKU có đủ lịch sử 90 ngày 15/07–12/10/2026, tập nghiên cứu còn **73 SKU và 6.570 bản ghi**. Tỷ lệ bán bằng 0 trong tập này là **56,8493%**; mức đóng góp GMV so với tập 94 SKU là **32,8403%**. Chỉ số là dữ liệu từ nguồn thứ ba, không phải đối soát giao dịch nội bộ.

## 2. Mục tiêu A – Dự báo khả năng phát sinh bán

Biến mục tiêu `SaleOccurred = 1` khi UnitsSold > 0, ngược lại = 0. Mô hình cho xác suất có phát sinh bán với horizon 1–7 tại từng forecast origin. Đặc trưng `Lag`, `Sum7/14/30`, tỷ lệ ngày bán, ADI/CV² tại origin, ngày mục tiêu, mã SKU và cờ HB GIFT lấy từ dữ liệu đến origin, không sử dụng nhãn tương lai.

Backtest theo 3 validation origins: 14/09, 21/09, 28/09/2026. Tuần holdout 06–12/10/2026 chỉ dùng đánh giá sau khi đã khóa mô hình/ngưỡng. Model/threshold lưu trong artefact Chương 6 là **Random Forest, threshold = 0,55**.

| Chỉ tiêu holdout | Giá trị thực nghiệm |
|---|---:|
| Quan sát SKU–ngày | 511 |
| F1 positive class | 0,808889 |
| Precision | 0,710938 |
| Recall | 0,938144 |
| Macro-F1 | 0,877468 |
| Average Precision | 0,794408 |
| ROC-AUC | 0,959709 |
| Brier Score | 0,068548 |
| Confusion matrix | TP=91, TN=377, FP=37, FN=6 |

Dự báo hồi cứu 13–19/10/2026: 511 dự báo SKU–ngày, tổng xác suất phát sinh bán **81,177959 SKU–ngày kỳ vọng**, nhãn dự báo có bán **77** (ngưỡng 0,55). Những giá trị này không biểu thị số lượng bán được hay số lượng cần nhập.

## 3. Mục tiêu C – Phân nhóm hành vi SKU

`ADI = ObservedDays / PositiveDays`; `CV² = (σ_positive / μ_positive)²`, σ là độ lệch chuẩn tổng thể. Ngưỡng ADI 1,32 và CV² 0,49. Các nhóm trên tập 73 SKU: Smooth 8; Erratic 9; Intermittent 33; Lumpy 14; không ghi nhận bán 9. Trong bản API mới, nhóm không ghi nhận bán được **gộp nhãn `Insufficient Data`** để đáp ứng cấu trúc báo cáo; `BehaviorDetail` giữ nguyên `No Sales` và phân biệt đầy đủ thông tin.

Những nhóm này mô tả hình thái lượng bán đã ghi nhận, không đồng nghĩa với phân khúc khách hàng hay tình trạng tồn kho.

## 4. Tự động hóa với n8n

Khi file lịch sử được cập nhật trên Google Drive, n8n tải CSV và gọi Python API. API kiểm tra tính liên tục, mã SKU và phạm vi mô hình, chạy pipeline `.joblib`, tính phân nhóm theo dữ liệu chốt và sinh 8 bảng CSV. n8n lưu kết quả vào thư mục Drive, rồi gửi báo cáo Telegram khi upload đầy đủ. Khóa SHA-256 + ModelVersion và cơ sở dữ liệu SQLite hỗ trợ chống xử lý trùng và ghi nhận trạng thái hoàn thành.

## 5. Giới hạn và diễn giải

- Dataset có nhiều ngày bằng 0 nhưng chưa đủ chứng minh nhu cầu thị trường bằng 0: thiếu tồn kho hay tình trạng listing có thể ảnh hưởng số bán ghi nhận.
- Mô hình được chọn trên validation cũ; chưa đánh giá với dữ liệu thực tế sau 12/10/2026. Khi nhận dữ liệu mới, hệ thống chỉ cảnh báo drift và **không tuyên bố đạt F1 tương tự**.
- SKU mới ngoài vocab mô hình chưa được dự báo; cần mở rộng dữ liệu, huấn luyện lại trên lịch sử có độ phủ phù hợp và đánh giá thời gian mới.
- N8n đóng vai trò điều phối; không trực tiếp huấn luyện model và không ra quyết định mua hàng tự động.
