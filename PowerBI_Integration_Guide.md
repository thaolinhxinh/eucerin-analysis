# TÍCH HỢP KẾT QUẢ ML AUTOMATION VÀO POWER BI

## 1. Nguồn và ý nghĩa các bảng

- `FactOccurrenceForecast_PowerBI.csv` — grain: **1 RunID × ProductID × ForecastDate**; gồm 7 horizon, ProbabilityOfSale ∈ [0,1], PredictedSaleFlag, DecisionThreshold, ModelVersion và BehaviorGroup. **Không có cột Units Sold dự báo**.
- `DimSKU_Behavior.csv` — grain: **1 RunID × ProductID**; ADI, CV², SaleRate, UnitsTotal, BehaviorGroup, BehaviorDetail và tên sản phẩm đã kiểm tra.
- `DimDate_Extended_For_Forecast.csv` — grain: **1 Date** từ đầu lịch sử đến hết tuần dự báo.
- `Model_Validation_Metrics.csv` và `Model_Holdout_Metrics.csv` — kết quả đánh giá từ ba validation folds và holdout Chương 6 của **bản mô hình đã huấn luyện**. Những file này không có kết quả kiểm thử trên dữ liệu mới.
- `Model_Run_History.csv` — ảnh chụp nhật ký tại lúc xuất file, có RunID, hash, model version và trạng thái ở thời điểm export. Trạng thái cuối cùng đọc từ API `/history`.
- `Monitoring_Daily_PowerBI.csv` — tổng xác suất theo ngày; đơn vị là **SKU kỳ vọng có phát sinh bán**, không phải số sản phẩm bán.
- `SKU_Monitoring_Alerts.csv` — danh sách cần **rà soát**, quy tắc hiện tại SaleRate ≥ 0,5 và (SaleRate − MeanForecastProbability) ≥ 0,3; **đây là heuristic minh họa, không phải dự báo tồn kho hoặc thiếu hàng**.

## 2. Kết nối dữ liệu

1. Trên Power BI Desktop, **Get Data → Text/CSV** từ các file đã xuất ra. Với Power BI Service, nên sử dụng nguồn Drive được đồng bộ vào nguồn hỗ trợ refresh hoặc lưu kết quả ở SharePoint/OneDrive/SQL; Google Drive dạng liên kết trực tiếp có thể không làm mới tự động như mong muốn.
2. Ép `ProductID`, `RunID`, `ModelVersion`, `RunSKUKey` thành **Text**, không đổi mã sản phẩm thành kiểu Number; `ForecastDate` và `Date` thành Date.
3. Quan hệ **1:n** `DimSKU_Behavior[RunSKUKey] → FactOccurrenceForecast_PowerBI[RunSKUKey]` (Single direction). `RunSKUKey = RunID & "|" & ProductID` đã được Python tạo sẵn để ngăn liên kết sai nếu nối nhiều lần chạy.
4. Quan hệ **1:n** `DimDate_Extended_For_Forecast[Date] → FactOccurrenceForecast_PowerBI[ForecastDate]` (Single direction).
5. Nếu muốn ghép vào bốn Dashboard BI đã có, tránh liên kết Fact Forecast trực tiếp với bảng Fact Sales qua ProductID, vì sẽ tạo nhân bản dòng và cộng trùng. Dùng Dim Product chung với quan hệ 1:n thích hợp hoặc bảng bridge đã chuẩn hóa.
6. **Luôn chỉ chọn một RunID** khi tính KPI hoặc so sánh mô hình theo từng lần dự báo; không cộng xác suất nhiều lần chạy vào nhau. Dùng slicer `RunID` hoặc tạo trang latest-run filter; cần phân biệt `as_of_date` với `ForecastDate`.

## 3. Measure DAX tối thiểu

```dax
Expected Selling SKU-Days =
SUM ( FactOccurrenceForecast_PowerBI[ProbabilityOfSale] )

Predicted Positive SKU-Days =
SUM ( FactOccurrenceForecast_PowerBI[PredictedSaleFlag] )

Average Sale Probability =
AVERAGE ( FactOccurrenceForecast_PowerBI[ProbabilityOfSale] )

SKUs In Forecast =
DISTINCTCOUNT ( FactOccurrenceForecast_PowerBI[ProductID] )

SKU Behavior Count =
DISTINCTCOUNT ( DimSKU_Behavior[ProductID] )
```

**Không** gọi `Expected Selling SKU-Days` là **Units Sold**, không nhân nó với giá bán để suy ra GMV. Đối với từng ngày, tổng xác suất là **số SKU kỳ vọng có phát sinh bán**; tổng qua 7 ngày là kỳ vọng số **SKU–ngày** có bán, một SKU có thể xuất hiện tối đa 7 lần.

## 4. Dashboard đề xuất: 05 | SKU Intelligence

KPI: Trained SKU, F1 holdout của mô hình, Mean Probability, Expected SKU-Days, 7-day predicted positive SKU-Days. Visual: phân bố nhóm hành vi (bar), scatter ADI–CV², đường Expected Selling SKUs theo ngày, SKU alerts (table), nhóm SKU có độ biến động lớn, slicer RunID/Date/BehaviorGroup. Ghi nguồn dữ liệu FastMoss bên thứ ba và phạm vi mô hình ngay trên trang dashboard.

## 5. Hạn chế

Dự báo A phân loại có bán/không bán, không dự báo lượng bán thực tế. Data Drift chỉ là tín hiệu thống kê so với dữ liệu huấn luyện, chưa phải giám sát accuracy trên dữ liệu mới. Model Version phải cố định theo lần chạy; muốn thêm SKU mới cần cập nhật notebook huấn luyện và thay model/metadata trong máy chủ.
