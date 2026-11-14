# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G02 (Lớp K5-Day6-L2-2A202603130) |
| Challenge | T02 · Raw QC Triage — Blurry, Glare & Underexposed Frames |
| Thành viên (5–6) + vai trò | 1. Vo Tien Phat (`phattiendo` — Lead / Integrator & Core PoC) · 2.Pham Duc Tho `thophamxt-bit` (Data Governance & Metric Contract) · 3.Nguyen Khanh Tung `sfpcshch` (QA & Edge-Case Testing) · 4. Nguyen Hoang Nhan `Nhan1724` (Human Review & Audit Evidence) · 5. Dinh Thanh Vinh (`vdprogramm` — Report & Failure Slice Analysis) |
| Git URL | https://github.com/phattiendo/K5-Day6-L2-2A202603130-VoTienPhat-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) | *(Cập nhật khi chốt tag)* |
| Tag `final-24h` (commit) | *(Cập nhật khi chốt tag cuối)* |
| Deadline (giờ VN) | 2026-11-15 14:00 (GMT+7) |
## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? ____
- Điểm nghẽn cụ thể: ____
- Đầu vào → đầu ra: ____
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): ____
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): ____

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | | | | |
| eval / heldout | | | | |

- Schema & class mapping: ____
- Seed: 42 · Cách chia split (theo scene/group/segment?): ____
- `manifest.csv` verified (sha256): có / không — lệnh: `python -m tools.verify_manifests`
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: ____

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: ____
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): ____
- Thành phần offline (model/weights + checksum + license nếu có): ____
- Trade-offs đã cân nhắc: ____

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): ____
- PoC (mô tả, version/config, commit): ____
- Cùng budget / cùng heldout / cùng seed: xác nhận ____

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: ______ | ____ | ____ | ____; higher/lower? |
| Hard-slice: ______ | ____ | ____ | ____; N=__ |
| Review@B / miss / FP | ____ | ____ | ____; B=__ |
| Runtime / 100 items | ____ | ____ | ____; CPU=__ |

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: ____ (xem `reports/metric_contract.md`)
- Threshold / budget B / K và lúc chốt: ____
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: ____
- Lệnh evaluate chính xác: `python -m src.evaluate --track t__ --pred ... --out ...`

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| `cam_A \| day` | 24 | Dễ bỏ sót lóa nắng cục bộ | Bắt chính xác `glare` & `blur` | Đo độ bão hòa vùng biển số kết hợp độ nét vùng đường |
| `cam_A \| dusk` | 16 | Nhiễu điểm số trung bình | Chuẩn hóa theo ngưỡng `dev` | Giảm báo động giả khi chuyển giao ánh sáng |
| `cam_A \| night` | 24 | Báo động giả hàng loạt (`dark`) | Phân tách được ảnh lỗi vs ảnh tối tự nhiên | Dùng chuẩn hóa bền vững (median/IQR) riêng cho slice đêm |
| `cam_B \| day` | 16 | Nhầm nền đường trơn với mờ | Bắt tốt khối nén JPEG (`compression`) | Kết hợp 4 đặc trưng thay vì 1 chỉ số Laplacian toàn ảnh |
| `cam_B \| night` | 16 | Gắn cờ gần như 100% ảnh | Lọc chính xác Top-K ca nghi lỗi nặng nhất | Giữ lại các khung hình vẫn đọc được biển số/vạch đường |

- **Failure case 1 (ảnh/metadata + root cause):** `img_01_2` (`cam_A | night`, `rank: 1`, `score: 1.0`, `reason: dark(z=58.58; b=0.0, d=58.6, g=0.0, c=0.2)`). *Root cause:* Thiếu sáng nghiêm trọng (underexposure) do đèn đường yếu vào ban đêm làm mất hoàn toàn chi tiết phương tiện và mặt đường; Reviewer (`Nhan1724`) xác nhận `approve` (`RECAPTURE`)[cite: 3].
- **Failure case 2 (ảnh/metadata + root cause):** `img_06_2` (`cam_B | night`, `rank: 3`, `score: 1.0`, `reason: compression(z=31.43; b=0.0, d=16.5, g=0.0, c=31.4)`). *Root cause:* Suy hao chất lượng do nén khối JPEG 8x8 quá mức kết hợp ánh sáng yếu tạo hiệu ứng vỡ ô vuông (blocking artifacts), không đủ điều kiện gán nhãn; Reviewer xác nhận `approve` (`RECAPTURE`)[cite: 3].
- **Latency / compute (máy, CPU, ms/item):** Chạy 100% offline trên CPU (`seed=42`), tổng thời gian xử lý 96 ảnh mất `~0.65s` (tương đương **~6.8 ms/item**, tức ~0.68s / 100 items), đáp ứng tốt yêu cầu kiểm tra nhanh tại biên (edge triage).
## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): ____
- Cách override + audit log (`out/audit_log.jsonl`): ____
- Decision policy + `reason_code` + owner: ____
- Khi nào HOLD/REWORK thay vì tự động release: ____

## 08 · Reproduce & tests

```bash
make setup          # hoặc: python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/<track> --config configs/lab.yaml --output out/ --offline --seed 42
python -m src.evaluate --track t__ --pred out/<file> --out reports/metrics_poc.json
pytest -q
```

- Output của `pytest -q`: ____
- Máy / CPU / OS / Python: ____ · git sha: ____

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:** Dữ liệu hình ảnh giao thông ngoài thực địa có khả năng chứa thông tin định danh cá nhân (PII) như biển số phương tiện và khuôn mặt người đi đường (thuộc phạm vi điều chỉnh của Nghị định 13/2023/NĐ-CP về Bảo vệ dữ liệu cá nhân). Để giảm thiểu rủi ro rò rỉ dữ liệu, toàn bộ pipeline QC của nhóm vận hành **100% offline** trên hạ tầng nội bộ, tuyệt đối không gửi ảnh thô lên các API đám mây bên thứ ba; file log kiểm toán (`out/poc/decision_log.csv`) chỉ lưu trữ `item_id`, mã băm `sha256` và các chỉ số kỹ thuật ẩn danh.
- **Điều chưa biết; false alarms; nếu scale 10× thì sao:** Với các khung hình biên vào ban đêm (`cam_A | night`), một số ảnh có độ sáng tổng thể thấp nhưng vùng biển số vẫn được đèn pha chiếu rõ vẫn có thể bị gắn cờ nhầm (`false alarm`), đòi hỏi bước duyệt thủ công (`Human-in-the-loop` qua `contact_sheet.html`) để điều chỉnh (`edit` $\rightarrow$ `KEEP`). Nếu mở rộng quy mô lên **10× (~1.000+ ảnh/lô)**, ngân sách duyệt tay cố định `B = 20` sẽ không bao quát hết vùng biên, cần nâng cấp cơ chế lấy mẫu phân tầng (stratified sampling) theo từng slice và tự động hóa bước làm mờ PII (face/plate blurring) trước khi đưa lên giao diện duyệt.
- **Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận:** Kết quả kiểm tra từ script và checklist kỹ thuật chỉ phục vụ mục đích kiểm soát chất lượng dữ liệu đầu vào (Data QC), không cấu thành chứng nhận tuân thủ pháp lý hay GDPR/Nghị định 13. Mọi giả định về thời hạn lưu trữ ảnh `RECAPTURE`, quyền truy cập của Reviewer và quy trình xóa dữ liệu gốc đều cần được DPO (Data Protection Officer) và bộ phận pháp chế phê duyệt chính thức trước khi triển khai thực tế.
- **Kế hoạch cải tiến:** Tích hợp thêm bộ phát hiện vùng biển số/khuôn mặt nhẹ chạy offline để vừa tính điểm chất lượng chính xác hơn tại vùng quan tâm (ROI), vừa tự động che mờ PII trước khi lưu trữ dài hạn.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Vo Tien Phat | `phattiendo` | Lead / Integrator & Core PoC (`src/pipeline.py`, `src/baseline_t02.py`, `configs/lab.yaml`)[cite: 3] | Dựng khung Baseline + PoC đa đặc trưng + Unit tests; merge cuối và gắn tag[cite: 3] | Có |
| Pham Duc Tho | `thophamxt-bit` | Data Governance & Metric Contract (`configs/lab.yaml`, `reports/metric_contract.md`)[cite: 3] | Cập nhật `group_id`, rà soát thông số ngưỡng/split và ký chốt `metric_contract.md`[cite: 3] | Có |
| Nguyen Khanh Tung | `sfpcshch` | QA & Edge-Case Testing (`tests/test_t02_pipeline.py`)[cite: 3] | Bổ sung unit test kiểm tra tính hợp lệ cột `score` (`[0, 1]`, không `NaN`) và trạng thái `decision.json`[cite: 3] | Có |
| Nguyen Hoang Nhan | `Nhan1724` | Human Review & Audit Evidence (`out/poc/review_queue_reviewed.csv`, `decision_log.csv`, `decision.json`)[cite: 3] | Thực hiện duyệt 20 ca biên trên `contact_sheet.html`, xuất CSV và ghi nhận cổng `REWORK` (46.9% lỗi)[cite: 3] | Có |
| Dinh Thanh Vinh | `vdprogramm` (`dinhthanhvinhnb205@gmail.com`) | Report & Failure Slice Analysis (`reports/group_report.md`)[cite: 3] | Hoàn thiện báo cáo nhóm, phân tích failure slices (`cam_A/cam_B`, `day/dusk/night`) và rủi ro PII/DPO[cite: 3] | Có |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| | | |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
