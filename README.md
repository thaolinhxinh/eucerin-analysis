# EUCERIN — Phương án B: Google Colab → Vercel → n8n → Telegram / Power BI

Bộ triển khai dựa trên pipeline A+C và mô hình Random Forest thực tế của Chương 6. **Không** sử dụng số liệu mô phỏng để thay thế kết quả Eucerin.

**Hosting chính: Vercel.** Production: [eucerin-ml-automation.vercel.app](https://eucerin-ml-automation.vercel.app). Repo riêng: [kl3485058-jpg/eucerin-ml-automation](https://github.com/kl3485058-jpg/eucerin-ml-automation), nhánh `main` tự deploy. Xem [`docs/VERCEL_DEPLOYMENT.md`](docs/VERCEL_DEPLOYMENT.md) và các hướng dẫn bên dưới. `render.yaml` vẫn được giữ lại cho môi trường Render.

## Tài liệu nên mở đầu tiên

- `docs/GIT_GITHUB_RENDER_DEPLOYMENT.md`: kết nối GitHub Private, Render Auto-Deploy, secrets, rollback và model versioning.
- `docs/VERCEL_DEPLOYMENT.md`: triển khai Vercel, lưu trữ bền vững và kết nối n8n.
- `docs/VERCEL_API_TEST_REPORT.md`: kết quả kiểm tra API production và dự báo dữ liệu thật.
- `docs/N8N_SETUP_GUIDE.md`, `docs/GOOGLE_DRIVE_SETUP.md`, `docs/TELEGRAM_SETUP.md`: cấu hình các credential còn thiếu.
- `docs/POWER_BI_INTEGRATION.md`: mô hình dữ liệu, relationships và DAX cho Dashboard 05.
- `docs/END_TO_END_TEST_REPORT.md`, `docs/CHAPTER_7_IMPLEMENTATION.md`: minh chứng và phạm vi đã triển khai.
- `QUICK_START.md`: các bước Vercel → Google Drive → n8n → Colab → Power BI.
- `DEPLOYMENT_CHECKLIST.md`: checklist để chạy thật và lấy minh chứng Chương 7.
- `render.yaml`: cấu hình Render paid + persistent disk cho SQLite chống gửi trùng.
- `n8n/EUCERIN_Vercel_EndToEnd.json`: workflow Vercel, có Manual/Schedule trigger; cần cấu hình OAuth và ID Drive/Telegram.
- `n8n/EUCERIN_Vercel_Error_Handler.json`: workflow báo lỗi riêng, không chứa token.
- `EUCERIN_ML_Training.ipynb`: notebook Colab huấn luyện, đánh giá và đóng gói mô hình.
- `PowerBI_Integration_Guide.md`: ghép CSV dự báo / phân nhóm vào Power BI.

## Kiểm thử nhanh bằng Docker
```bash
# copy .env.example thành .env, thay ML_API_KEY bằng secret thật (không commit)
docker compose up --build
# mở http://localhost:10000/health
```

## Kiểm thử Python không cần Docker
```bash
python -m pip install -r requirements-dev.txt -r requirements.txt
pytest -q
node tests/test_n8n_js.js
```

**Lưu ý:** Bản Render giữ lại để tham khảo. GitHub → Vercel Auto-Deploy đã kết nối; Google Drive OAuth, Telegram Bot credential/chat ID và Power BI refresh vẫn cần cấu hình tại các dịch vụ tương ứng. Không có credential nào được đưa vào repo.
