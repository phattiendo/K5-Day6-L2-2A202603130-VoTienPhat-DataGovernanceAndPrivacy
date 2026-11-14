# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | `T02` — Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Primary metric (tên đúng như evaluator in ra) | `Defect Recall@B`  |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | `image`|
| Công thức + numerator / denominator | $\text{Defect Recall@B} = \frac{\|\text{Top-}B \cap P\|}{\|P\|}$ — **Numerator**: số ảnh lỗi thật (`gt.is_defect == 1`) nằm trong Top-$B$ của `ranked_review.csv` (lọc trên `eval`); **Denominator**: tổng số ảnh lỗi thật (`gt.is_defect == 1`) trong tập `eval`. Kèm $\text{Precision@B} = \frac{\|\text{Top-}B \cap P\|}{B}$ (Denominator = $B = 20$). |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Ghép chính xác 1–1 theo khóa định danh `image_id` , sắp xếp giảm dần theo `score` , lấy Top-$B$ phần tử đầu tiên. Với metric phụ `Defect-type accuracy (GT defects)`, khớp chuỗi chính xác `pred_defect_type == gt.defect_type` trên các mẫu `gt.is_defect == 1`. |
| Candidate pool cố định | Toàn bộ 96 ảnh synthetic $320\times 180$ từ 24 cảnh gốc trong `fixtures/t02_raw_qc/images.csv`; khi đánh giá chính thức lọc cố định trên `split == "eval"` ($N_{\text{eval}} = 40$ ảnh / 10 cảnh gốc). |
| Review budget B / K | `B = 20` ảnh có `score` cao nhất được đưa vào `review_queue.csv` / `contact_sheet.html` để human review và chấm Top-$B$. |
| Seed | `42` |
| Threshold policy (chọn trên dev như thế nào) | Chỉ hiệu chỉnh thống kê tham chiếu và chốt ngưỡng trên `split == "dev"` ($N_{\text{dev}} = 56$ ảnh / 14 cảnh gốc), tuyệt đối không đọc `gt/` và không tune trên `eval`:<br>1. **Baseline (`src/baseline_t02.py`)**: Dùng độ nét toàn ảnh `score = 1 / (1 + laplacian_variance)`, ngưỡng `baseline_lap_threshold = 120.0` (`lap < 120.0` $\rightarrow$ `RECAPTURE` / `blur`, ngược lại `KEEP` / `none`).<br>2. **PoC (`src/pipeline.py`)**: Chuẩn hóa Robust Z-score ($\text{median}, 1.4826\times\text{MAD}$) neo trên `dev` theo từng slice `(camera_id, light)` cho độ nét vùng đường (`log_lap`) & nén JPEG (`blockiness_raw`), và theo `light` cho thiếu sáng (`dark_raw`) & lóa vùng biển số ROI (`glare_raw`). Điểm hợp nhất `raw_score = 0.75 * max_z + 0.25 * l2_z` qua hàm sigmoid tâm `sigmoid_center = 1.50`. Ngưỡng chốt trên `dev`: `z_defect_threshold = 1.35` (`max_z >= 1.35` $\rightarrow$ `RECAPTURE`, gán nhãn theo thành phần $z$ lớn nhất; `max_z < 1.35` $\rightarrow$ `KEEP` / `none`).<br>3. **Decision Gate (`decide()`)**: `rework_rate_threshold = 0.25` (nếu chưa có human review `n_reviewed == 0` $\rightarrow$ `HOLD`; sau human review nếu `recapture_rate > 0.25` $\rightarrow$ `REWORK`, ngược lại `GO`). |
| Eval split (không dùng để tune) | `split = eval` ($N_{\text{eval}} = 40$ ảnh thuộc 10 cảnh gốc: `img_01`, `img_03`, `img_05`, `img_06`, `img_13`, `img_15`, `img_16`, `img_17`, `img_19`, `img_23`; chia theo cảnh gốc để chống data leakage với `dev`). |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | 1. **False alarm in top-B**: tỷ lệ ảnh sạch  bị đưa nhầm vào Top-$B$ (`clean images in top-B / clean images`), đặc biệt ở slice `light=night` và `camera_id=cam_B`.<br>2. **Missed defect Rate** ($1 - \text{Defect Recall@B}$, `lower` tốt): ảnh lỗi thật bị sót ngoài Top-$B$. |
| Slices sẽ báo cáo (≥2) | 1. Theo điều kiện ánh sáng `light`: `light=day` ($N_{\text{eval}}=20$), `light=dusk` ($N_{\text{eval}}=4$), `light=night` ($N_{\text{eval}}=16$).<br>2. Theo loại lỗi `defect_type`: `defect=blur`, `defect=glare`, `defect=dark`, `defect=compression`.<br>3. Theo tổ hợp thiết bị – ánh sáng `camera_id\|light` (`cam_A\|day`, `cam_A\|dusk`, `cam_A\|night`, `cam_B\|day`, `cam_B\|dusk`, `cam_B\|night`) trong queue kiểm duyệt. |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Báo cáo **95% Wilson score confidence interval** (`src.metrics.estimation.wilson_ci(k, n, alpha=0.05)`) cho các tỷ lệ (`Defect Recall@B`, `Precision@B`, `False alarm in top-B`) kèm theo phân số tuyệt đối `numerator / denominator` do cỡ mẫu `eval` ($N=40$, $B=20$) và một số slice (như `light=dusk`, $N=4$) nhỏ. |
| Ngày giờ chốt + người chốt | `2026-11-14 15:55 GMT+7` — Người chốt & ký tên: **Phạm Đức Thọ_2a202603182**  |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
