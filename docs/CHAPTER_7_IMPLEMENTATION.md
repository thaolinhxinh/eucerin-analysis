# Chương 7 — Triển khai và kiểm chứng hệ thống

## Kiến trúc

GitHub `kl3485058-jpg/eucerin-ml-automation` nhánh `main` kích hoạt Vercel production deploy. FastAPI nạp frozen Random Forest đã huấn luyện; `/predict-file` xác thực CSV rồi tạo dự báo occurrence T+1..T+7 và phân nhóm ADI/CV². Postgres giữ run ledger/acknowledgements; private Vercel Blob giữ CSV output; n8n được thiết kế làm orchestration từ Google Drive, upload tám bảng CSV, rồi gửi Telegram. Power BI đọc các bảng export.

```text
Google Drive CSV → n8n → Vercel FastAPI + frozen model
                                ├─ Postgres: idempotency/run state
                                └─ Private Blob: CSV exports
          n8n ← downloads/acks ─┘
           ├─ Google Drive output history
           ├─ Telegram summary/error alert
           └─ Power BI (refresh cần cấu hình riêng)
```

## Kết quả kiểm chứng

Ngày 2026-11-19, production deploy `dpl_BnnrFr7SMuCSmrgN1dF69npVqB9k` trả health HTTP 200 với model loaded và forecast ready. Gửi CSV Eucerin thật (8,030 dòng nguồn, 94 SKU; 21 SKU ngoài vocabulary model) nhận lại run đã có theo idempotency: `20261012_4d874af41e_3ab947a5`, model `3ab947a5f8113fea`, origin 2026-10-12, forecast 2026-10-13 đến 2026-10-19: 73 SKU, 511 SKU–ngày, 77 nhãn bán dự báo tại threshold 0.55, tổng probability 81.177959 SKU–ngày kỳ vọng có bán. Tám artifact private tải được; run vẫn `prepared`, chưa được Drive upload. Đây là replay trên tập nghiên cứu Chương 6; không đại diện forecast hiện tại hoặc lượng bán.

Random Forest validation pooled: F1 0.8569, precision 0.7850, recall 0.9433, ROC-AUC 0.9606 (N=1,533). Holdout 2026-10-06–12: F1 0.8089, precision 0.7109, recall 0.9381, ROC-AUC 0.9597, Brier 0.0685 (N=511). Các số này lấy từ CSV metric đã lưu, không tính trên forecast tương lai.

## Thành phần bàn giao và giới hạn

- API có auth cho route nghiệp vụ, CSV validation, model schema/version, forecast 7 ngày, ADI/CV², output Power BI, idempotency theo input hash + model version, Postgres/Blob trên Vercel và SQLite/filesystem local.
- Workflow JSON có Manual Trigger, lịch 09:00 ICT, Drive metadata/download/upload, retry hữu hạn cho HTTP, artifact acknowledgements, reservation chống gửi lặp và Error Handler đã làm sạch thông tin.
- Kiểm thử local dùng mock/fixture cho lifecycle Drive/Telegram; production API được gọi bằng CSV thật và trả run theo idempotency. Không chạy workflow trên n8n instance thật.
- Drive OAuth, Telegram Bot credential/chat ID, bật workflow và Power BI Service gateway/workspace còn cần người dùng cấu hình. Không khẳng định tự refresh Power BI hoặc gửi Telegram đã chạy.
- Cold start, tải đồng thời và memory peak chưa đo; production call đo 19.9 giây end-to-end, model artifact 3.61 MB, CSV 2.99 MB.
- Dữ liệu dừng tại 2026-10-12; model chưa retrain. Cảnh báo là danh sách rà soát, không phải kết luận hết hàng/reorder.

Các bước cài đặt xem `N8N_SETUP_GUIDE.md`, `GOOGLE_DRIVE_SETUP.md`, `TELEGRAM_SETUP.md` và `POWER_BI_INTEGRATION.md`.
