# Triển khai EUCERIN bằng GitHub và Render

## Kiến trúc và trạng thái lưu trữ

VS Code/Git quản lý mã và phiên bản; GitHub Private lưu repository; Render Blueprint build Docker và tự deploy commit mới trên `main`. API dùng model đã đóng gói, không retrain khi deploy. n8n gọi API bằng HTTPS và credential Header Auth `X-API-Key`, rồi ghi CSV vào Google Drive; Power BI đọc các CSV ở Drive.

`render.yaml` khai báo dịch vụ Docker `eucerin-ml-api`, health check `/health`, `ML_API_KEY` nhập riêng ở Render và persistent disk 1 GB tại `/app/storage`. Disk yêu cầu plan có hỗ trợ persistent disk (Blueprint hiện đặt `starter`, có phí). Render Free không hỗ trợ persistent disk; dữ liệu local trên Free có thể mất khi restart/deploy. Chỉ SQLite và file kết quả ghi dưới `/app/storage` được lưu bền vững.

Repository giữ model `models/Model_Classification.joblib` (~3.5 MiB), cấu hình model, code, notebook, tests và workflow n8n. Git bỏ qua CSV nguồn lịch sử `reference/historical_eucerin_confirmed.csv`, output sinh ra, `.env`, credentials, SQLite, log và cache. Docker chỉ đóng gói hai metric CSV cần cho reporting, không đóng gói dữ liệu lịch sử. Cung cấp source CSV riêng cho n8n/Drive; không thêm vào Git để làm test.

Model hiện tại là 3,613,442 bytes, thấp hơn giới hạn 100 MiB/file của GitHub. Render không công bố giới hạn riêng cho model file trong Git-backed Docker build; tài liệu Render nêu giới hạn build là 16 GB disk và 120 phút, còn giới hạn image nén 10 GB áp dụng cho deploy ảnh prebuilt. Docker chưa được cài trong môi trường này nên chưa đo được kích thước image cuối cùng. Tham khảo [GitHub repository limits](https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits), [Render build limits](https://render.com/docs/build-pipeline) và [Render prebuilt image requirements](https://render.com/docs/deploying-an-image).

## Tạo repository và kết nối lần đầu

1. Đăng nhập GitHub trong trình duyệt, tạo repository **Private** `eucerin-ml-automation`; để trống repository, không tạo README/license nếu local đã có commit.
2. Mở Terminal trong VS Code tại thư mục dự án. Kiểm tra `git status --short --branch` và xác nhận URL repository trong trang GitHub thuộc đúng tài khoản của bạn.
3. Nếu chưa có remote, thêm URL HTTPS thật do GitHub hiển thị (không thay bằng tên người dùng phỏng đoán):

   ```bash
   git remote add origin https://github.com/<GITHUB_OWNER>/eucerin-ml-automation.git
   git remote -v
   ```

4. Xác nhận repository là Private trong GitHub, nhánh local là `main`, và không có file bí mật/dữ liệu riêng trong stage. Sau đó push:

   ```bash
   git push -u origin main
   ```

5. Nếu Git hỏi xác thực, dùng Git Credential Manager hoặc đăng nhập GitHub theo hướng dẫn của VS Code/GitHub. Không gửi token qua chat, không đưa token vào URL, file `.env` hay lệnh được lưu trong lịch sử shell.
6. Trên Render Dashboard chọn **New → Blueprint**, kết nối GitHub nếu được yêu cầu, chọn đúng repository private `eucerin-ml-automation` và Blueprint `render.yaml`. Xác nhận branch `main`, Docker runtime, plan phù hợp và disk `/app/storage`.
7. Nhập giá trị `ML_API_KEY` trực tiếp ở form Blueprint/Environment Variables. Dùng một khóa ngẫu nhiên dài; không dùng giá trị ví dụ. Bật Auto-Deploy theo commit (Blueprint đặt `autoDeployTrigger: commit`). Không cần đặt `PORT`: Render cấp biến này cho Web Service.

## Quy trình cập nhật code

Trước khi stage, xem file thay đổi và kiểm tra secrets. Sau khi xác nhận `git diff --cached` chỉ có nội dung dự kiến:

```bash
git status
git add .
git diff --cached
git commit -m "Update Eucerin ML automation"
git push origin main
```

Push thành công lên `main` sẽ kích hoạt Render build/deploy. Không tự động train lại model. Dùng commit riêng, mô tả rõ thay đổi và model version.

## Kiểm tra triển khai và logs

1. Render Dashboard → service `eucerin-ml-api` → **Events/Deploys** để xem commit, trạng thái build/start và deploy mới nhất.
2. Mở **Logs** để đọc build logs (Docker build/pip install) và runtime logs (khởi động Uvicorn, lỗi import/model/storage). Sửa nguyên nhân rồi push commit mới; Render sẽ deploy lại.
3. Khi deploy báo live, kiểm tra `https://<service>.onrender.com/health`. Kết quả cần có `status: ok`, `model_version` và `trained_skus`. HTTP 503 nghĩa là model/config không load được hoặc khởi động chưa sẵn sàng; xem runtime logs.
4. Gửi CSV đầy đủ qua HTTPS với API key trong header, không query string:

   ```powershell
   $apiKey = $env:ML_API_KEY
   curl.exe -H "X-API-Key: $apiKey" -F "file=@C:/path/to/eucerin-full-history.csv;type=text/csv" "https://<service>.onrender.com/predict-file"
   ```

   Trong PowerShell, đặt `$env:ML_API_KEY` trong phiên terminal trước khi dùng `curl.exe`. Không lưu khóa vào script. Endpoint kết quả trả `run_id`; tải từng file qua `/results/{run_id}/{file_name}` với cùng header. Endpoint `/predict-file` chỉ nhận CSV đầy đủ, giới hạn 20 MiB; kiểm tra `forecast_rows`, cảnh báo và `model_version` trong response.
5. Chỉ sau khi API test thành công mới cấu hình n8n: base URL HTTPS của Render; Header Auth credential có tên `X-API-Key` và giá trị trùng `ML_API_KEY`; credential Google Drive và Telegram cấu hình riêng. Import workflow không tự tạo credential hoặc bật workflow. Chạy Manual Trigger, kiểm tra Drive upload và Telegram, rồi mới bật lịch.

## Khi deploy thất bại

- **Build thất bại:** đọc build log, kiểm tra lệnh `pip install`, Dockerfile và file bị thiếu. Thử build local nếu Docker đã cài.
- **Container thoát ngay:** đọc runtime log; xác minh model/config cùng feature schema, phiên bản dependency, `PORT` và biến `STORAGE_DIR=/app/storage`.
- **Health check 503:** `/health` cố load model. Kiểm tra hai file trong `models/`, model version, log import/joblib và Blueprint có trỏ đúng root repository.
- **401:** đặt header chính xác `X-API-Key` trong n8n credential; so sánh với Render Environment Variables mà không ghi giá trị vào log.
- **CSV trả 422:** kiểm tra UTF-8 CSV, cột bắt buộc, ngày đầy đủ và scope SKU; API không tự điền ngày thiếu bằng 0.
- **Run state bị mất hoặc storage không ghi được:** kiểm tra plan có persistent disk, mount `/app/storage`, `STORAGE_DIR` trùng mount path và log quyền ghi. Free không giữ filesystem sau restart.
- Sau khi sửa, commit/push lên `main` và theo dõi deploy mới. Không xóa database hoặc reset disk để khắc phục lỗi nếu chưa đối soát run đang chờ.

## Rollback an toàn

Ưu tiên revert commit lỗi bằng một commit mới để giữ lịch sử và cho Render tự deploy phiên bản trước:

```bash
git log --oneline -5
git revert <BAD_COMMIT_SHA>
git push origin main
```

Nếu commit lỗi đã được chia sẻ, không reset/force push. Theo dõi Render deploy của commit revert và kiểm tra `/health`. Disk không bị xóa bởi thao tác revert; thay đổi schema SQLite phải tương thích ngược trước khi phát hành.

## Environment variables và secrets

- Render: `ML_API_KEY` là secret bắt buộc; `APP_MODE=production`, `MODEL_DIR=/app/models`, `STORAGE_DIR=/app/storage` và `PYTHONUNBUFFERED=1` đã khai báo trong Blueprint.
- Local: sao chép `.env.example` thành `.env`, thay placeholder bằng khóa test riêng. `.env` bị ignore; không commit hoặc chia sẻ.
- n8n: lưu API key trong Credentials → Header Auth (`X-API-Key`), không đặt trong Code node/JSON. Google Drive OAuth và Telegram bot token dùng credential tương ứng.
- Nếu secret bị lộ, rotate tại dịch vụ phát hành và cập nhật nơi dùng; xóa khỏi file hiện tại không xóa được lịch sử Git đã commit.

## Cập nhật model

1. Train và đánh giá trong `EUCERIN_ML_Training.ipynb`/Colab; việc deploy không retrain.
2. Chỉ phát hành artifact đã được xác thực: `models/Model_Classification.joblib` và `models/Model_Config.json` phải cùng phiên bản, đúng `feature_columns`, threshold và feature contract trong `app/chapter6_pipeline.py`.
3. Chạy kiểm tra model/API với source CSV được cung cấp riêng. `tests/test_api.py` dùng file mặc định trong workspace hoặc biến `EUCERIN_TEST_DATA`; nếu không có CSV, test tích hợp sẽ báo skip.
4. Cập nhật hai artifact cùng một commit, ghi model version/hash và kết quả đánh giá trong mô tả commit/tài liệu. Không commit dữ liệu nguồn hoặc CSV output làm bằng chứng thử nghiệm.
5. Push `main`, theo dõi Render deploy, kiểm tra `model_version` và `/health`, rồi mới chạy workflow n8n.
