# EUCERIN — Colab + Vercel + n8n + Google Drive + Telegram

Vercel production đã được deploy và health/inference API đã được kiểm tra bằng CSV Eucerin lịch sử. Google Drive OAuth, Telegram credentials và chạy workflow end-to-end vẫn cần cấu hình theo các hướng dẫn bàn giao. Xem [`docs/VERCEL_DEPLOYMENT.md`](docs/VERCEL_DEPLOYMENT.md); Render vẫn có thể dùng theo tài liệu tùy chọn bên dưới.

## 1. Vercel

1. Project hiện có `kien-e0d4/eucerin-ml-automation`, đã kết nối GitHub private `kl3485058-jpg/eucerin-ml-automation`, nhánh `main`; push lên nhánh này sẽ tạo production deploy.
2. Kết nối Postgres và private Blob từ Vercel Marketplace; bảo đảm project có `DATABASE_URL` và biến kết nối Blob.
3. Đặt `ML_API_KEY` bằng secret ngẫu nhiên và `APP_MODE=production` trong Production Environment Variables.
4. Production URL là `https://eucerin-ml-automation.vercel.app/health`; API cần trả `status: ok`, `model_loaded: true` và `forecast_ready: true`.
5. Import `n8n/EUCERIN_Vercel_EndToEnd.json` cùng `n8n/EUCERIN_Vercel_Error_Handler.json`. Production `apiBaseUrl` đã được đặt sẵn; gắn Header Auth `X-API-Key` khớp `ML_API_KEY`.
6. CSV nhận vào Vercel tối đa 4 MiB. Không bật lịch workflow trước khi chạy thử Drive và Telegram bằng tay.

**Luồng:** Google Drive CSV → n8n đọc file → Vercel FastAPI chạy Random Forest có sẵn + ADI/CV² → n8n tải 8 CSV và upload vào Drive → Telegram. Notebook Colab dùng để huấn luyện lại khi có dữ liệu bổ sung được kiểm chứng.

## Render (tùy chọn)

1. Tạo một **GitHub repository Private** tên `eucerin-ml-automation`, để trống (không khởi tạo README/license nếu đang đẩy lịch sử local).
2. Trong terminal VS Code, kiểm tra `git status`, thêm `origin` bằng URL repository đó, rồi push nhánh `main`. Xem `docs/GIT_GITHUB_RENDER_DEPLOYMENT.md` để biết lệnh và quy trình kiểm tra secrets.
3. Vào https://dashboard.render.com/ → **New > Blueprint** → kết nối repository private `eucerin-ml-automation`, nhánh `main`, rồi chọn `render.yaml`.
4. Bản chính dùng **plan: starter** và persistent disk 1 GB ở `/app/storage` (có phí). Kiểm tra chi phí hiện hành trên Render trước khi xác nhận.
5. Render hỏi giá trị `ML_API_KEY`: tạo secret dài ngẫu nhiên, lưu trong password manager và nhập trực tiếp vào Render Environment Variables. Không dán vào Git, workflow JSON hoặc chat.
6. Deploy xong, mở `https://<your-render-service>.onrender.com/health`. Cần hiện `status: ok`, `trained_skus` từ model (hiện là 73). Đây là kiểm tra API sống, chưa chứng minh workflow n8n đã chạy thật.
7. Kiểm tra log và xác nhận `APP_MODE=production`. CSV hiện có kết thúc ngày 12/10/2026; kết quả thử nghiệm đó không chứng minh chất lượng trên dữ liệu mới.

**Render Free chỉ để demo:** nếu muốn thử không mất phí, thay `render.yaml` bằng nội dung `render-free-demo.yaml` trước khi push. Free không giữ dữ liệu sau restart/deploy, nên **không bật lịch tự động hoặc kỳ vọng chống gửi trùng**. Hệ thống đầy đủ cần disk bền vững.

## 2. Google Drive

- Trong Google Drive tạo thư mục `Eucerin_Source` và `Eucerin_ML_Outputs`.
- Upload **CSV lịch sử đầy đủ** vào Source; file `reference/historical_eucerin_confirmed.csv` không được lưu trong GitHub nên cần lấy từ bản dữ liệu được phê duyệt hoặc dùng file đã có trong Drive. Không upload một ngày đơn lẻ hay Google Sheet ở định dạng gốc.
- Từ link chia sẻ lấy **File ID** CSV và **Folder ID** output.
- Các lần cập nhật phải thêm quan sát cho ngày mới của đủ các SKU thuộc mô hình, không tự điền 0 khi không có xác nhận từ nguồn.

## 3. n8n

1. Import `EUCERIN_Render_n8n_Workflow.json` và `EUCERIN_Render_Error_Handler.json`.
2. Mở node **02 | Config - Render, Drive, Telegram** và sửa bốn giá trị `apiBaseUrl`, `sourceFileId`, `outputFolderId`, `telegramChatId`; không nhập API key vào node này.
3. Gán **Google Drive OAuth2 credential** cho các node Get / Download / Upload.
4. Trên các HTTP Request chọn Authentication → Generic Credential Type → Header Auth. Tạo một credential Header Auth: **Name: `X-API-Key`**, **Value: giá trị `ML_API_KEY` đúng trên Render**. Gán cho mọi node HTTP Request thuộc workflow chính.
5. Tạo Telegram bot bằng @BotFather, khai báo credential bot trong n8n rồi gán cho node `16 | Telegram: Send summary` và node Telegram của error workflow. Lấy chat ID của người nhận đã bắt đầu trò chuyện với bot.
6. Trên workflow chính: **Settings → Error Workflow**, chọn error handler đã import. Đặt timezone Asia/Ho_Chi_Minh (đã có trong JSON, vẫn kiểm tra khi import).
7. **Execute Workflow** bằng Manual Trigger; kiểm tra các node. Đặc biệt `02 | Drive: Get source metadata` phải có `id` và `md5Checksum` hoặc `modifiedTime` hoặc `version`.
8. Chỉ bật Active/Schedule Trigger khi quy trình upload 8 CSV và gửi Telegram chạy thành công.

## 4. Colab và mô hình

- Upload `EUCERIN_ML_Training.ipynb` vào https://colab.research.google.com/
- Notebook so sánh các thuật toán và xuất bộ mô hình, metadata; **không tự động deploy Render**.
- Chỉ thay `models/Model_Classification.joblib`, `models/Model_Config.json` cùng feature contract khi đã huấn luyện lại, kiểm tra mô hình và version tương thích. Commit lại repository để Render redeploy.

## 5. Kiểm tra và khắc phục

- Render `/health` trả 503 → thiếu/cấu hình mô hình sai; xem logs.
- Render 403/401 từ API → kiểm tra n8n Header Auth `X-API-Key`; không gửi qua query string.
- Drive metadata báo thiếu revision → node Get có thể không trả metadata; kiểm tra n8n phiên bản và output trước khi đổi workflow, không tự đặt revision giả.
- API 422 thiếu ngày → file CSV không đầy đủ; không tự thêm 0.
- Không upload được Drive → kiểm tra quyền ghi thư mục output; xóa file bị trùng nếu từng upload rồi mà Ack thất bại. Chạy lại cùng source có thể tạo file trùng sau khi lỗi giữa upload và Ack: đối chiếu trên Drive thủ công.
- Telegram lỗi giữa gửi và xác nhận → API giữ `notification_reserved` để chặn gửi lặp; kiểm tra Telegram và sửa thủ công khi cần.
- Power BI: dùng CSV trong output folder qua phương thức được hỗ trợ (sync OneDrive/SharePoint hoặc tải CSV từ Drive), **Drive upload không tự refresh Power BI Service**.

## 6. Hạn chế minh bạch

- Model đóng băng tại dữ liệu đến 12/10/2026; phiên bản dùng để nghiên cứu. Data Drift hoặc thời gian quá xa sẽ có cảnh báo. Không coi khả năng dự báo tương lai đã được bảo chứng.
- SKU mới không nằm trong từ vựng mô hình sẽ được bỏ qua và báo trong warnings cho đến khi huấn luyện lại.
- Quy trình nhận bản ghi CSV đầy đủ, **không kết nối trực tiếp API FastMoss/TikTok Shop**.
- Render là dịch vụ HTTP tự động; Google Colab chỉ dùng train/retrain.
- Chưa chạy kiểm thử tương tác thật trên tài khoản Render, Google Drive, n8n hay Telegram ở môi trường tạo gói.
