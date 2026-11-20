# Power BI — Dashboard 05: SKU Intelligence

Workflow tạo các CSV theo mỗi run: `FactOccurrenceForecast_PowerBI.csv`, `DimSKU_Behavior.csv`, `DimDate_Extended_For_Forecast.csv`, `Model_Run_History.csv`, `Model_Validation_Metrics.csv`, `Model_Holdout_Metrics.csv`, `Monitoring_Daily_PowerBI.csv`, và `SKU_Monitoring_Alerts.csv`.

## Kết nối file riêng tư

CSV nằm trong Google Drive riêng tư. Không dùng liên kết “Anyone with the link” để Power BI đọc file. Phương án có sẵn và ít phụ thuộc nhất là đồng bộ thư mục Drive bằng Drive for desktop, sau đó trong Power BI Desktop chọn **Get data → Folder** tới thư mục output; Power Query lọc đúng file prefix và combine file cùng schema. Dữ liệu cục bộ có thể refresh trong Desktop.

Để Power BI Service refresh được thư mục trên máy, cần cài và duy trì online On-premises data gateway, đăng ký đúng Folder data source và cấu hình credentials/refresh trong semantic model. Nếu không có gateway, có thể dùng một kho cloud mà Power BI Service truy cập trực tiếp (ví dụ SharePoint/OneDrive nếu tổ chức có), nhưng cần bổ sung luồng đồng bộ và quyền truy cập riêng. Chỉ upload CSV lên Google Drive không tự làm Power BI refresh. Xem [Microsoft hướng dẫn scheduled refresh](https://learn.microsoft.com/en-us/power-bi/connect-data/refresh-scheduled-refresh) và [Text/CSV connector](https://learn.microsoft.com/en-us/power-query/connectors/text-csv).

## Star schema

- Trong Power Query, kiểm tra `ForecastDate` và `DimDate_Extended_For_Forecast[Date]` được chuyển sang kiểu **Date** trước khi tạo relationship; không để chúng là Text nếu connector không tự nhận diện ngày ISO.
- `FactOccurrenceForecast_PowerBI[RunSKUKey]` → `DimSKU_Behavior[RunSKUKey]` (many-to-one). Fact CSV có cột này; nếu dimension CSV cũ chưa có, tạo calculated column `RunSKUKey = DimSKU_Behavior[RunID] & "|" & DimSKU_Behavior[ProductID]` trong Power BI. Mỗi dimension được snapshot theo run.
- `FactOccurrenceForecast_PowerBI[ForecastDate]` → `DimDate_Extended_For_Forecast[Date]` (many-to-one, Date dimension phía 1).
- `FactOccurrenceForecast_PowerBI[RunID]` → `Model_Run_History[run_id]` (many-to-one; dùng one-way filter từ dimension/history sang fact).
- `Model_Validation_Metrics` và `Model_Holdout_Metrics` là các bảng metric theo `ModelVersion`; không nối trực tiếp tới ngày dự báo. Dùng `ModelVersion` để lọc hoặc tạo `DimModel` sau khi kiểm tra phiên bản.
- `Monitoring_Daily_PowerBI` và `SKU_Monitoring_Alerts` là bảng tổng hợp/giám sát riêng; tránh cộng lại chúng với fact forecast trong cùng visual.

`FactOccurrenceForecast_PowerBI` là forecast; không chứa actual label của ngày tương lai. Holdout metrics có nhãn thật cho khoảng 2026-10-06 đến 2026-10-12. Không tính F1/precision/recall từ forecast tương lai khi chưa có actual.

## Measures mẫu (DAX)

```DAX
Forecast SKU Count = DISTINCTCOUNT(FactOccurrenceForecast_PowerBI[ProductID])
Expected Selling SKU-Days = SUM(FactOccurrenceForecast_PowerBI[ProbabilityOfSale])
Predicted Selling SKU-Days = SUM(FactOccurrenceForecast_PowerBI[PredictedSaleFlag])
Mean Sale Probability = AVERAGE(FactOccurrenceForecast_PowerBI[ProbabilityOfSale])
Holdout F1 = CALCULATE(MAX(Model_Holdout_Metrics[F1]), Model_Holdout_Metrics[Model] = "Random Forest")
Holdout Precision = CALCULATE(MAX(Model_Holdout_Metrics[Precision]), Model_Holdout_Metrics[Model] = "Random Forest")
Holdout Recall = CALCULATE(MAX(Model_Holdout_Metrics[Recall]), Model_Holdout_Metrics[Model] = "Random Forest")
Holdout ROC-AUC = CALCULATE(MAX(Model_Holdout_Metrics[ROCAUC]), Model_Holdout_Metrics[Model] = "Random Forest")
```

Card `Expected Selling SKU-Days` cần lọc đúng một RunID và khoảng ngày; đây là tổng xác suất của các SKU–ngày. Không đổi nhãn thành units sold. Dùng `BehaviorGroup` cho phân bố ADI/CV²; dùng `SKU_Monitoring_Alerts` làm danh sách review, không đặt tên “stock-out” hay “reorder”.

## Chọn run mới nhất

Lọc `Model_Run_History` theo `created_at` mới nhất rồi truyền `run_id` qua relationship tới fact. Kiểm tra status: chỉ coi các hàng `delivered` là workflow đã hoàn thành; run kiểm thử production ngày 2026-11-19 đang `prepared` và chưa được upload. `Model_Run_History.csv` là snapshot khi forecast tạo; để biết trạng thái hiện tại chính xác, API có endpoint `/history` cần Header Auth, hoặc dùng status của run theo `GET /runs/{run_id}`.

## Refresh và kiểm soát

Trong Desktop, dùng **Refresh** để nạp CSV đã đồng bộ. Trong Power BI Service, cấu hình gateway online và schedule chỉ khi gateway/nguồn dữ liệu đã được thiết lập và quyền phù hợp. Đây là hướng dẫn, không phải cấu hình refresh đã làm; chưa có workspace/credential Power BI trong môi trường triển khai này.
