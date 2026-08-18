# Cách dùng bằng chứng số — API định tính

Áp dụng cho **v2 · v3 · v4**, mọi công ty. Cập nhật 2026-08-07.

---

## 1. Một câu tóm tắt

> Đọc `metric_expected` **trước**. Nó cho biết câu hỏi này có đòi số liệu hay không.
> Ba trường hợp, xử lý khác nhau — và **không trường hợp nào được suy số ra từ đoạn văn**.

---

## 2. Ba trường hợp

```
metric_expected = false   ->  metric_status = "not_expected"    72/95 muc
metric_expected = true    ->  metric_status = "found_table"     15/95 muc
metric_expected = true    ->  metric_status = "not_found"        8/95 muc
```

### 2a. `not_expected` — câu không hỏi số (72 mục)

**Không đổi gì so với trước.** Đọc `items[]` như cũ. Không có `metric_evidence`.
Ba trường mới (`metric_expected` · `metric_status` · `metric_absence`) chỉ là thêm vào, không
ảnh hưởng cách đọc.

### 2b. `found_table` — có bảng số (16 mục)

Đọc theo §3.

### 2c. `not_found` — câu hỏi số nhưng không tìm được (7 mục)

```jsonc
"metric_expected": true,
"metric_status": "not_found",
"metric_absence": { "reason": "no_candidate | below_threshold | blocked_by_gate",
                    "best_score": 0.46, "threshold": 0.48, "n_candidates_seen": 41 }
```

**Cách xử lý: để trống ô số, viết phần định tính từ `items[]`.**
**Cấm suy số ra từ đoạn văn** — đoạn văn hay có năm (`2025년`), số trang, tiêu chí giải thưởng.

Đọc `reason` để biết trách nhiệm thuộc về ai:

| `reason` | nghĩa | làm gì |
|---|---|---|
| `no_candidate` | nguồn thật sự không có | hỏi công ty |
| `below_threshold` | **hệ thống có tìm thấy nhưng chưa đủ điểm** | báo lại cho team RAG, đừng kết luận "công ty không công bố" |
| `blocked_by_gate` | có nhưng bị cổng chặn | báo lại cho team RAG |

---

## 3. Đọc bảng số — 5 bước

> ### ★★ ĐỌC `metric_evidence`, ĐỪNG ĐỌC `items[]`
>
> Đây là lỗi phổ biến nhất. `items[]` là **bản gộp rút gọn cho client cũ** — mỗi block chỉ
> **1 hàng đại diện**, và nếu nhiều block thì nó **bỏ bớt block**.
>
> Ví dụ thật, cùng một câu `Q039`:
>
> ```
> metric_evidence  ->  23 hang / 5 block      <- BANG DAY DU, dung cai nay
> items[]          ->   3 hang / 3 block      <- ban gop, MAT 2 block
> normalized_answer_ko ->  1 hang             <- chi la dong dai dien
> ```

```
0. Doc `metric_summary` de biet quy mo    <- MOI
1. Nhom metric_evidence theo `table_block`      (moi block = 1 bang cua 1 phap nhan)
2. Doc `block_role`      <- QUAN TRONG NHAT
3. Doc `entity_class`    <- truoc khi dung BAT KY con so nao
4. Trong moi block: dong 합계 / 총 / 소계 dung dau
5. `top_k` = so BLOCK primary, khong phai so hang. Tra it hon top_k la BINH THUONG.
```

```jsonc
"metric_summary": { "n_rows": 23, "n_blocks": 5,
                    "n_primary": 17, "n_scope_variant": 4, "n_denominator": 2 }
```

### `block_role` — ba loại

| giá trị | nghĩa | dùng thế nào |
|---|---|---|
| **`primary`** | đúng chỉ tiêu, đúng phạm vi | **số chính của báo cáo** |
| `scope_variant` | đúng chỉ tiêu, **khác pháp nhân** (nhà máy, holding, công ty liên quan) | chỉ dùng khi báo cáo cần mức nhà máy/pháp nhân đó |
| `denominator` | mẫu số (`매출`, `생산량`) để tính `원단위` | **không bao giờ là đáp án** |

### ★ Ba điều cấm

```
1. CAM cong `scope_variant` voi `primary`   -> khac phap nhan, cong vao la sai bao cao
2. CAM dung `denominator` lam so dap an      -> no la mau so, khong phai chi tieu
3. CAM dung so ma khong doc `entity_class`   -> cung ten chi tieu, khac phap nhan, khac gia tri
```

---

## 4. Ba danh sách trong response

| trường | chứa gì | dùng khi |
|---|---|---|
| **`metric_evidence`** | **tất cả** hàng số, đủ mọi block (cả 3 `block_role`) | **dựng bảng số — dùng cái này** |
| `narrative_evidence` | đoạn văn | dựng phần diễn giải |
| `items[]` | bản gộp cho client cũ: mỗi block `primary` **1 hàng đại diện** + luôn ≥2 đoạn văn. Bị giới hạn bởi `top_k` nên **có thể mất block** | chỉ dùng nếu client chưa nâng cấp |
| `normalized_answer_ko` | **một** dòng đại diện | hiển thị nhanh, **không phải** đáp án đầy đủ |

`items[]` **không bao giờ** chứa `scope_variant`. Ngân sách của `metric_evidence` và
`narrative_evidence` là **riêng** — bảng số không đẩy đoạn văn ra ngoài.

### ★ Đừng bỏ qua `narrative_evidence` khi đã có bảng

Bảng số **không chứa** công thức, phạm vi áp dụng, và thay đổi cách ghi nhận. Ví dụ thật:

```
"용수 재사용률(%) = 용수 재사용량 / 용수 사용량 × 100"                <- CONG THUC
"2024년부터 ㈜대웅제약·대웅바이오 국내사업장으로 적용범위 변경"          <- DOI PHAM VI
"2022년 청구월 기준 -> 실제 사용기간으로 변경"                        <- CHUOI SO DUT GAY
```

Không đọc ba dòng đó thì không biết chuỗi 2022–2025 **không so sánh trực tiếp được**.

---

## 5. Gọi API

```jsonc
{ "company_id": "daewoong", "question_ids": ["Q039"], "top_k": 5 }
```

- Gửi 1 id → nhận **đúng 1** kết quả. Gửi nhiều id → `results` theo **đúng thứ tự** gửi.
- `question_ids` rỗng → trả tất cả.
- Id không tồn tại → bỏ qua, ghi vào `warnings`.
- `top_k` với metric = **số block primary** (mặc định 5); mỗi block tối đa 12 hàng.

---

## 6. Ví dụ

**Có bảng** — `Q039` (용수 사용 및 폐수 배출) — thực tế trả **23 hàng / 5 block**:

```jsonc
"metric_expected": true, "metric_status": "found_table",
"metric_summary": { "n_rows": 23, "n_blocks": 5, "n_primary": 17,
                    "n_scope_variant": 4, "n_denominator": 2 },
"metric_confidence": null,  // nhieu phap nhan + scope_variant = dung, khong phai low
"metric_evidence": [        // <- 23 hang, day du. Duoi day chi trich 3.
  { "table_block": "6.용수 > 대웅제약 용수사용", "block_rank": 1, "block_role": "primary",
    "entity": "대웅제약", "entity_class": "daewoong_pharm",
    "raw_evidence_ko": "... > 취수량 합계 | 톤 | 2023=... | 2024=... | 2025=..." },
  { "table_block": "6.용수 > 그룹용수사용",    "block_rank": 2, "block_role": "primary",
    "entity": "대웅그룹", "entity_class": "group_total", ... },
  { "table_block": "6.용수 > 대웅제약 용수사용", "block_role": "denominator",
    "raw_evidence_ko": "... > 매출 | 억원 | ..." }        // <- KHONG phai dap an
]
```

→ Dựng **hai bảng riêng** (제약 và 그룹), không gộp. `매출` chỉ để tính `원단위`.

**Không có bảng** — `Q095` (이해관계자 소통):

```jsonc
"metric_expected": true, "metric_status": "not_found",
"metric_absence": { "reason": "no_candidate", "n_candidates_seen": 0 }
```

→ Để trống ô số. Viết phần định tính từ `items[]`.

---

## 7. Lưu ý bản hiện tại

| mục | lưu ý |
|---|---|
| `metric_confidence` | `"low"` **chỉ** khi `pct_ON` đã đo trên hàng **primary đang trả** < 90% (nhãn `m8_judge_rows` + `m11_rows_c`), hoặc override đo tay. **Không** bật vì có nhiều pháp nhân / `scope_variant`. |
| **Hai mục đang mang `low`** | `Q019` (đo 75%, lẫn hàng **đào tạo** thay vì sự cố) · `Q027` (đo 80%, có hàng khác phạm vi lọt vào `primary`). Đối chiếu từng hàng trước khi dùng. **13 mục còn lại không có cờ = đã đo và đạt.** |
| `metric_summary` | nhìn phát biết `n_rows` / `n_blocks` — **đừng** đếm `items[]` để lấy bảng. |
| Số nằm trong câu văn | **chưa bật.** Câu như `"교육은 연 2회 실시"` hiện **không** được đánh dấu là số liệu. Đã đo, chưa đủ cỡ mẫu để bật. |
| `metric_form` | hiện **luôn là `table_row`**. Chỉ khi bật số-trong-câu-văn mới xuất hiện `inline_figure`. |
| 8 mục `not_found` | `Q011 · Q015 · Q023 · Q043 · Q051 · Q055 · Q083 · Q095` |

---

## 8. Bảng tra nhanh

```
metric_expected == false            ->  doc items[] nhu cu, het.

metric_status  == "found_table"     ->  doc METRIC_EVIDENCE (khong phai items[])
                                        -> nhom theo table_block
                                        -> loc block_role == "primary"
                                        -> doc entity_class truoc khi dung so
                                        -> VAN doc narrative_evidence (cong thuc, pham vi)

metric_status  == "not_found"       ->  de trong o so.  CAM suy so tu doan van.
                                        doc metric_absence.reason de biet bao ai.
```

**Ba lỗi hay gặp nhất**

```
1. Doc items[] de lay bang        ->  mat hang, mat ca block.  Doc metric_evidence.
2. Cong scope_variant voi primary ->  khac phap nhan, sai bao cao.
3. Suy so tu doan van khi not_found ->  doan van co nam, so trang, tieu chi giai thuong.
```
