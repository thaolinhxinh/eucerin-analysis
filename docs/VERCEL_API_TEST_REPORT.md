# Báo cáo kiểm thử API Vercel

Ngày kiểm tra: 2026-11-19 (Asia/Ho_Chi_Minh). Production URL được xác nhận qua `vercel project inspect`: https://eucerin-ml-automation.vercel.app.

## Health

`GET /health` trên deployment production mới trả HTTP 200 với `status=ok`, `model_loaded=true`, `forecast_ready=true`, `model_version=3ab947a5f8113fea`, `trained_skus=73`, `mode=production`. Deployment `dpl_BnnrFr7SMuCSmrgN1dF69npVqB9k` (commit `389ba82`) ở trạng thái Ready. Lần đo trước redeploy mất 0,615 giây; thời gian lần health mới không được ghi lại.

## Dự báo bằng dữ liệu Eucerin thật

Đã gửi `reference/historical_eucerin_confirmed.csv` qua `POST /predict-file` từ một script cục bộ. CSV được gửi multipart/form-data, field `file`, kèm `source_id` và SHA-256 làm `source_revision`; API key dùng header `X-API-Key` đọc từ file local bị Git ignore, không ghi vào log. Sau production redeploy, request thứ hai xác nhận API vẫn trả HTTP 200/`ready` cho cùng run theo idempotency; lần đó mất 24,360 ms và không tạo run mới hay gửi lại Telegram.

| Kết quả | Giá trị thực đo |
|---|---:|
| HTTP / API status | `200` / `ready` |
| Thời gian request end-to-end | 19,887 ms |
| Request CSV | 2,992,985 bytes |
| Response JSON | 2,738 bytes |
| Model version | `3ab947a5f8113fea` |
| Ngày chốt lịch sử | 2026-10-12 |
| Khoảng dự báo | 2026-10-13 đến 2026-10-19 |
| SKU trong model / forecast | 73 / 511 SKU–ngày |
| SKU–ngày gắn nhãn bán ở ngưỡng 0,55 | 77 |
| Tổng xác suất | 81.177959 SKU–ngày kỳ vọng có bán, không phải Units Sold |
| SKU mới chưa có trong model | 21, bị loại khỏi forecast và cảnh báo yêu cầu xem xét retrain |
| File export được API tạo | 8, hiện chờ n8n upload/acknowledge lên Drive |

Run ID: `20261012_4d874af41e_3ab947a5`. Postgres cho thấy run này được tạo ngày 2026-11-19 00:08 ICT và vẫn `prepared`; request kiểm tra resume/trả lại run hiện có theo idempotency, không tạo run mới. Cả tám endpoint `/results/{run_id}/{filename}` trả HTTP 200, `text/csv`, kích thước từ 379 đến 138,388 bytes. Đây là replay dữ liệu lịch sử Chương 6, không phải dự báo mới tính đến ngày 2026-11-19. Run đang chờ đồng bộ vì chưa upload Drive hoặc gửi Telegram.

## Kích thước và giới hạn

- Artifact `models/Model_Classification.joblib`: 3,613,442 bytes.
- Vercel function được cấu hình tối đa 300 giây; app từ chối CSV lớn hơn 4 MiB để chừa chỗ cho multipart. Request đo được khoảng 2.86 MiB, dưới giới hạn.
- Lần chạy thực tế 19.9 giây, response 2.7 KB. Một request thành công không chứng minh giới hạn RAM, cold start hoặc tải đồng thời; các mục này chưa được đo.
- Hệ thống dùng Postgres cho ledger và private Vercel Blob cho artifacts; `/tmp` chỉ là vùng làm việc tạm.

## Metrics nghiên cứu đã lưu

Không tính lại metric từ forecast chưa có nhãn thật. `reference/Validation_Metrics.csv` ghi Random Forest pooled validation: N=1,533, threshold=0.55, F1=0.8569, Precision=0.7850, Recall=0.9433, ROC-AUC=0.9606. `reference/Holdout_Metrics.csv` ghi holdout 2026-10-06 đến 2026-10-12: N=511, F1=0.8089, Precision=0.7109, Recall=0.9381, ROC-AUC=0.9597, Brier=0.0685. Đây là số liệu nghiên cứu Chương 6, không phải đánh giá trên dữ liệu mới.

## Phạm vi chưa được chứng minh

Chưa có lần chạy n8n thật với Google Drive OAuth/Telegram credential; chưa gửi tin thật; Power BI chưa được kết nối hoặc refresh. Không suy ra nhu cầu hay thiếu hàng từ alert chênh lệch lịch sử và xác suất.
