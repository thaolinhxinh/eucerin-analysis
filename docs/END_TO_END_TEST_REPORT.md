# Báo cáo kiểm thử end-to-end

Ngày 2026-11-19. Kiểm tra thực tế và kiểm thử cục bộ được tách biệt:

| Thành phần | Bằng chứng | Trạng thái |
|---|---|---|
| Vercel production health | Deployment `dpl_BnnrFr7SMuCSmrgN1dF69npVqB9k`, `GET /health`: HTTP 200, model loaded/forecast ready, model `3ab947a5f8113fea`, 73 SKU | Đã xác minh |
| Production inference | CSV Eucerin thật: HTTP 200, `ready`, 511 SKU–ngày, model version khớp; post-deploy request trả cùng run idempotently | Đã xác minh; replay lịch sử |
| API response size/runtime | 2,738 byte response, request 2,992,985 byte, 19.887 giây end-to-end | Đã đo một lần |
| Local API/model/integration | `pytest -q`: 24 passed; test dùng CSV Eucerin local và frozen model | Đã xác minh |
| n8n Vercel Code nodes | `node tests/test_n8n_js.js`: PASS | Đã xác minh bằng Code node VM; chưa chạy trên n8n thật |
| Drive/Telegram thực | OAuth/bot credential chưa được gắn, không gửi message thật | Chưa chạy |
| Power BI | Chưa có workspace/semantic model/gateway | Chưa kết nối |

Lệnh `pytest -q` ban đầu lỗi do pytest thu thập nhầm `smoke_test.py` và truyền `-q` như URL. `pytest.ini` hiện giới hạn collection về `tests/`; lần chạy cuối đã qua.

Chi tiết production prediction, giới hạn và metric Chương 6 ở [`VERCEL_API_TEST_REPORT.md`](VERCEL_API_TEST_REPORT.md). Run ID lịch sử hiện còn `prepared`, file export chờ n8n upload; không có Drive acknowledgement hay Telegram message giả.
