---
title: "[LangGraph][V3] Daewoong ESG Project & Run Comparison"
source_format: html
report_date: 2026-08-10
languages:
  - vi
  - ko
default_language: vi
version: V3
rendering_notes:
  theme: slate-teal
  max_content_width_px: 1200
  layout: tabbed-dashboard
  status_colors: green-amber-red
---

> **Mục đích sử dụng:** Đây là nguồn nội dung Markdown để tái tạo báo cáo HTML song ngữ. Phần tiếng Việt và tiếng Hàn được tách thành hai chương hoàn chỉnh. Khi dựng lại giao diện, có thể dùng frontmatter để phục hồi theme slate–teal, bố cục dashboard rộng 1.200 px, các tab theo chương và màu trạng thái xanh–vàng–đỏ.

## Mục lục nội dung

1. Tổng quan dự án
2. Luồng xử lý hiện tại
3. Các vai trò và chức năng trong hệ thống
4. Các cải thiện đã triển khai
5. So sánh hai lần chạy Daewoong gần nhất
6. Điểm còn yếu và nơi cần cải thiện
7. Chú thích thuật ngữ và mã kỹ thuật
8. Kết luận

## Đặc tả để dựng lại báo cáo

- **Ngôn ngữ:** có nút chuyển `VI`/`KO`; chỉ hiển thị một chương ngôn ngữ tại một thời điểm.
- **Khung trang:** nền `#f3f5f6`, nội dung rộng tối đa `1200px`, font Arial/Malgun Gothic/Noto Sans KR, line-height khoảng `1.58`.
- **Hero:** nền slate `#243746`, chữ trắng, viền dưới teal `#08796d`; bốn chỉ số chính trình bày thành bốn card trên desktop.
- **Điều hướng:** thanh tab sticky phía trên, mỗi chương nội dung tương ứng một tab; tab đang chọn dùng màu blue `#3d5db3`.
- **Panel và card:** panel trắng, viền `#dbe2e6`, bo góc 7–8px; card dùng viền trên theo nhóm màu blue/teal/green/amber/red.
- **Trạng thái:** PASS dùng green `#257747`; WARN dùng amber `#a76b13`; FAIL dùng red `#b44833`; thông tin dùng blue `#3d5db3`.
- **Bảng:** header nền `#edf1f3`, có cuộn ngang trên màn hình hẹp. Các ô gộp dọc trong HTML nguồn đã được lặp lại ở từng dòng Markdown để không mất ngữ nghĩa.
- **Responsive:** lưới bốn cột chuyển thành hai cột dưới `980px` và một cột dưới `650px`; luồng sáu bước cũng co về hai rồi một cột.
- **Bản in:** ẩn thanh tab và nút đổi ngôn ngữ; hiển thị liên tiếp toàn bộ panel, bỏ shadow, giữ màu nền hero.

# Bản tiếng Việt

Báo cáo kiến trúc và vận hành · Daewoong ESG 2025 · 10/08/2026

## ESG LangGraph: tổng quan dự án và so sánh hai lần chạy gần nhất

V3

Báo cáo trình bày cách hệ thống hoạt động, cách phân chia trách nhiệm và kết quả thực tế của Daewoong giữa lần chạy ngày 07/08/2026 và 10/08/2026. Báo cáo tách riêng hai vấn đề: hệ thống đọc được nhiều dữ liệu hơn và câu trả lời cuối có thực sự tốt hơn hay không.

[↗ Mở báo cáo Daewoong mới nhất trên Google Drive](https://docs.google.com/spreadsheets/d/1-QwR51i7RMo4wghsE8pT-fRYTO1TIqODWJr6djOsQUI/edit?usp=drive_web&ouid=112413599409010031174)

- **95 + 210** — mục định tính và định lượng trong một báo cáo

- **34** — vai trò: 10 vai trò chung + 24 AI chuyên viết ESG

- **31** — chức năng nhỏ có thể thử lại, giới hạn thời gian và ghi nhật ký

- **75 → 113** — mục định lượng có giá trị, tăng 38

_Toàn cảnh hệ thống_

### Tổng quan dự án

Hệ thống tạo báo cáo ESG riêng cho từng công ty và từng năm. Dữ liệu có thể được đọc từ tệp JSON hoặc nhận qua API, tức cổng kết nối với hệ thống dữ liệu khác; cấu hình hiện tại dùng API. Công cụ LangGraph sắp xếp thứ tự xử lý 95 câu định tính. Với 210 mục định lượng, hệ thống lấy và điền giá trị trực tiếp, không nhờ AI viết lại.

**API**

Nhận dẫn chứng định tính và số liệu định lượng theo đúng công ty, năm báo cáo.

**2 luồng**

Một luồng quản lý toàn bộ báo cáo; một luồng chi tiết xử lý từng câu định tính.

**Tách từng câu**

Qxxx chỉ dùng dữ liệu dẫn chứng của chính câu đó, tránh lẫn dữ liệu giữa 95 câu.

**Excel**

Xuất câu trả lời, kết quả kiểm tra, số liệu và bảng đối chiếu nguồn.

#### Đầu vào và đầu ra

#### Đầu vào theo công ty

- Tên công ty, `company_id`, ngành, quy mô và năm báo cáo.
- Evidence định tính theo Q001-Q095, gồm narrative và metric evidence.
- Câu trả lời định lượng từ API cho template 210 mục.
- Template rules theo ngành và quy mô, item contracts và writer profiles.

#### Đầu ra theo từng run

- JSON câu trả lời định tính, checklist QA và dữ liệu định lượng đã map.
- Partial checkpoint sau từng item để tiếp tục khi timeout/quota lỗi.
- Excel cuối có 4 sheet: báo cáo chính; định lượng (`Quantitative`); bảng số liệu định tính (`Qualitative Metrics`); và dữ liệu nguồn để đối chiếu (`Metric Evidence Audit`).
- Nhật ký ghi lại từng bước, từng chức năng và câu trả lời. LangSmith hỗ trợ xem chi tiết các lần gọi AI; Temporal hỗ trợ điều phối công việc chạy lâu khi được bật.

> **Đánh giá tổng quát.**
>
> Cách phân chia trách nhiệm hiện tại đã rõ và người dùng có thể truy lại nguồn. Vấn đề chính không còn là thiếu luồng xử lý, mà là dữ liệu dẫn chứng từ API chưa đủ, số trong câu có bảng chưa được đối chiếu ổn định và việc kiểm tra rồi viết lại còn tốn thời gian.

_Sơ đồ xử lý_

### Luồng xử lý hiện tại

Luồng báo cáo quản lý toàn bộ một lần chạy, từ lúc nhận dữ liệu đến lúc xuất Excel. Bên trong bước `generate_qualitative` (sinh phần định tính), 95 câu dùng chung một quy trình mẫu nhưng mỗi câu có vùng dữ liệu, quy tắc và AI chuyên viết riêng. Vì vậy dữ liệu của câu này không được đưa sang câu khác.

#### Luồng toàn báo cáo · 6 bước

- **01 · Khởi tạo** — `initialize_run`: tạo thư mục kết quả và đọc cấu hình, ngành, mẫu báo cáo.

- **02 · Nhận dữ liệu** — `load_company_input`: gọi API hoặc đọc tệp đúng công ty và năm.

- **03 · Sắp xếp dữ liệu** — `normalize_evidence`: đưa dữ liệu định tính và định lượng về cùng cấu trúc.

- **04 · Viết 95 câu** — `generate_qualitative`: xử lý từng câu, kiểm tra toàn bộ và chỉnh văn phong.

- **05 · Điền 210 số liệu** — `map_quantitative`: lấy giá trị trực tiếp, không dùng AI viết.

- **06 · Xuất kết quả** — `write_outputs`: ghi tệp dữ liệu, kết quả kiểm tra, bản lưu tạm và Excel cuối.

#### Luồng xử lý một câu định tính · 17 bước kỹ thuật, gom thành 10 nhóm dễ hiểu

- **1 · Đọc quy tắc của câu** — Mỗi Qxxx có yêu cầu riêng về dữ liệu, cách viết và kiểm tra.

- **2 · Chọn đúng dữ liệu** — Kiểm tra công ty, năm, mã câu; tách đoạn mô tả và dòng số liệu.

- **3 · Chia đoạn dẫn chứng** — Chia đoạn dài thành phần nhỏ để đọc, nhưng không đổi nội dung gốc.

- **4 · Lọc phần liên quan** — AI chỉ đánh dấu phần phù hợp hoặc không phù hợp với câu hỏi; không viết lại dẫn chứng.

- **5 · Kiểm tra đủ dữ liệu** — Xác định dẫn chứng đã đủ chưa và chọn các ý quan trọng để gửi cho AI viết.

- **6 · Chọn chuyên gia ESG** — Chuyển câu đến đúng một trong 24 AI chuyên viết theo chủ đề.

- **7 · Viết bản đầu** — AI viết câu trả lời tiếng Hàn, chỉ dựa trên dữ liệu đã được chấp nhận.

- **8 · Sửa hình thức** — Kiểm tra ngôn ngữ, ký tự lỗi và cách trình bày trước khi đánh giá.

- **9 · Kiểm tra hai lớp** — Quy tắc cố định kiểm tra số liệu/hình thức; AI kiểm tra bịa đặt, thiếu ý và mâu thuẫn.

- **10 · Viết lại hoặc kết thúc** — Câu chưa đạt có thể được viết lại rồi kiểm tra lại; câu thiếu hoặc sai dẫn chứng được dừng và đánh dấu rõ.

#### Cách xử lý câu định tính có bảng số liệu

#### 1 · Đọc từng dòng bảng

API V3 gửi các dòng số liệu. Hệ thống phân biệt dòng kết quả chính, dòng tổng dùng để tính tỷ lệ và dòng có phạm vi khác, đồng thời giữ nguyên đơn vị và nhóm bảng.

#### 2 · Chuẩn bị dữ liệu cho AI

Các dòng kết quả phù hợp được nhóm theo cùng một bảng và cùng đối tượng trước khi đưa vào nội dung hướng dẫn cho AI. Phần mô tả dài chỉ giữ các ý quan trọng.

#### 3 · AI viết lời, hệ thống dựng bảng

AI viết phần giải thích bằng lời. Bảng trong Excel được dựng trực tiếp từ dữ liệu có cấu trúc, không để AI tự nhớ hoặc tự sắp số; một sheet riêng lưu dữ liệu để đối chiếu.

_Phân chia trách nhiệm_

### Các vai trò và chức năng trong hệ thống

**Agent** là một vai trò AI hoặc vai trò xử lý có trách nhiệm rõ ràng, ví dụ nhận dữ liệu, kiểm tra dẫn chứng hoặc viết câu trả lời. **AgentSkill** là một chức năng nhỏ mà vai trò đó có thể sử dụng, ví dụ “chia dẫn chứng”, “kiểm tra câu trả lời” hoặc “xuất Excel”. Mỗi chức năng có giới hạn thời gian, có thể thử lại khi lỗi và có ghi nhật ký để theo dõi. Tệp manifest là danh sách khai báo vai trò nào dùng mô hình AI, nội dung hướng dẫn và chức năng nào.

**10**

vai trò chung quản lý toàn bộ quy trình.

**24**

AI chuyên viết theo 24 nhóm chủ đề ESG, bao phủ đủ 95 câu.

**31**

chức năng nhỏ có thể kiểm tra và thay thế riêng mà không đổi toàn bộ luồng.

#### 10 vai trò chung

| Agent                           | Vai trò chính                                                   | Nhóm skill   |
| ------------------------------- | --------------------------------------------------------------- | ------------ |
| `report_orchestrator_agent`     | Khởi tạo run, load static config, resolve sector.               | Bootstrap    |
| `input_data_agent`              | Đọc API/file và normalize dữ liệu công ty.                      | Input        |
| `template_policy_agent`         | Chọn template rule theo ngành, quy mô và item.                  | Policy       |
| `evidence_retrieval_agent`      | Scope, segment, relevance, coverage và Evidence focus.          | Evidence     |
| `qualitative_item_policy_agent` | Load/validate contract riêng Q001-Q095.                         | Contract     |
| `esg_writer_router_agent`       | Đảm bảo mỗi item thuộc đúng một expert writer.                  | Routing      |
| `qualitative_reviewer_agent`    | Kiểm tra bằng quy tắc cố định, kiểm tra bằng AI và gộp kết quả. | Kiểm tra     |
| `style_editor_agent`            | Batch review, style rewrite, final polish và re-judge.          | Style        |
| `quantitative_mapper_agent`     | Map 210 mục định lượng không qua LLM.                           | Quantitative |
| `excel_report_agent`            | Ghi các tệp kết quả, bản lưu tạm và Excel cuối.                 | Xuất tệp     |

#### 24 AI chuyên viết theo chủ đề ESG

Mỗi AI chuyên viết phụ trách một nhóm chủ đề và một danh sách câu cụ thể. Hồ sơ của từng AI nêu rõ kiến thức cần có, nội dung cần ưu tiên và lỗi cần tránh. Tất cả vẫn tuân theo cùng quy tắc về dẫn chứng và kiểm tra chất lượng.

- **Quản lý ESG** — Q001-Q003

- **An toàn và sức khỏe nghề nghiệp** — Q004-Q007

- **Lao động và nhân quyền** — Q008-Q011

- **An toàn sản phẩm** — Q012-Q015

- **Bảo mật thông tin** — Q016-Q019

- **Quản lý môi trường** — Q020-Q023

- **Đạo đức kinh doanh** — Q024-Q027

- **Hành động khí hậu** — Q028-Q031

- **Kinh tế tuần hoàn** — Q032-Q035

- **Quản lý nước** — Q036-Q039

- **Đa dạng sinh học** — Q040-Q043

- **Ô nhiễm và phát thải** — Q044-Q047

- **Sản phẩm bền vững** — Q048-Q051

- **Trách nhiệm sản phẩm** — Q052-Q055

- **Nguồn nhân lực** — Q056-Q059

- **Đa dạng và hòa nhập** — Q060-Q063

- **Chuỗi cung ứng có trách nhiệm** — Q064-Q067

- **Tác động cộng đồng** — Q068-Q071

- **Quản trị ủy ban** — Q072-Q075

- **Cơ cấu hội đồng quản trị** — Q076-Q079

- **Hệ thống vận hành ESG** — Q080-Q083

- **Tuân thủ** — Q084-Q087

- **Sở hữu và vận hành** — Q088-Q091

- **Giao tiếp với các bên liên quan** — Q092-Q095

#### 31 chức năng nhỏ theo từng nhóm công việc

| Nhóm công việc               | Số chức năng | Công việc chính                                                                                |
| ---------------------------- | ------------ | ---------------------------------------------------------------------------------------------- |
| Khởi tạo & nhận dữ liệu      | 6            | Đọc cấu hình, ngành, mẫu, dữ liệu công ty; sắp xếp dữ liệu và chọn quy tắc                     |
| Dẫn chứng & quy tắc từng câu | 8            | Làm sạch, chọn đúng câu, chia đoạn, lọc liên quan, đánh giá độ đầy đủ và kiểm tra quy tắc      |
| Chọn chuyên gia & viết câu   | 9            | Chọn AI chuyên viết, chuẩn bị nội dung theo 4 nhóm, viết bản đầu, viết lại và sửa hình thức    |
| Kiểm tra & văn phong         | 6            | Kiểm tra quy tắc, AI đánh giá, gộp kết quả, kiểm tra toàn bộ, viết lại và chỉnh văn phong cuối |
| Định lượng & xuất tệp        | 2            | Điền 210 số liệu, ghi JSON và Excel                                                            |

Tổng số được đối chiếu trực tiếp với danh sách đăng ký chức năng trong code (`build_default_skill_registry`): 31 chức năng.

_Những thay đổi đã làm_

### Các cải thiện đã triển khai

So với phiên bản trước, hệ thống đã tách dữ liệu dẫn chứng theo từng câu tốt hơn, đọc được bảng số liệu trong phần định tính, tạo thêm bảng đối chiếu nguồn và có thể tiếp tục từ kết quả đã lưu nếu lần chạy bị gián đoạn.

#### 1 · Không trộn dẫn chứng

Khi dùng API, hệ thống kiểm tra công ty, năm và mã câu rồi chỉ đưa dữ liệu đúng Qxxx vào xử lý. Hệ thống không tìm lại trên kho dữ liệu chung của 95 câu.

#### 2 · Giữ nguyên nội dung nguồn

Đoạn mô tả dài được chia nhỏ nhưng không bị viết lại. Dữ liệu gốc từ API được giữ để đối chiếu; bản đã chia chỉ dùng làm đầu vào cho AI.

#### 3 · Kết hợp AI và bảng cố định

AI viết phần giải thích, còn bảng số liệu được dựng trực tiếp từ dữ liệu nguồn. Hệ thống đã nhận diện 23 câu cần bảng và thêm các sheet để truy lại nguồn.

#### 4 · Kiểm tra hai lớp

Lớp quy tắc cố định kiểm tra hình thức và số liệu. Lớp AI kiểm tra thông tin bịa đặt, ý bị bỏ sót và nội dung mâu thuẫn. Câu đã sửa phải được kiểm tra lại.

#### 5 · Quy tắc riêng cho từng câu

Q001-Q095 có yêu cầu riêng, giúp sửa logic của một câu mà ít ảnh hưởng đến câu khác. AI không được tự thêm lời giải thích về dữ liệu không có.

#### 6 · Có thể tiếp tục khi bị lỗi

Mỗi chức năng có thời gian chờ và số lần thử lại riêng. Kết quả được lưu dần theo từng câu; nhật ký cho biết bước nào, câu nào bị lỗi.

#### Cải thiện đo được ở lần chạy 10/08/2026

| Chỉ số                                                              | 07/08/2026 | 10/08/2026 | Nhận xét                                     |
| ------------------------------------------------------------------- | ---------- | ---------- | -------------------------------------------- |
| Định lượng có giá trị                                               | 75         | 113        | +38 (+50,7%)                                 |
| Mục định lượng đã được điền, mã trạng thái `filled`                 | 70         | 104        | +34                                          |
| Câu cần bảng số liệu được nhận diện                                 | 0          | 23         | Chức năng mới                                |
| Dòng kết quả chính trong bảng được chấp nhận (`primary Metric row`) | -          | 110/118    | 93,2%                                        |
| Câu đạt kiểm tra chất lượng (`QA PASS`)                             | 3          | 5          | +2                                           |
| Câu bị AI đánh giá nội dung không đạt (`LLM Judge failed`)          | 7          | 4          | −3                                           |
| Câu bỏ sót ý quan trọng đã có trong dẫn chứng (`answer omission`)   | 5          | 3          | −2                                           |
| Câu có cách mở đầu lặp lại với nhiều câu khác (`repeated opening`)  | 2          | 0          | Không còn phát hiện trong danh sách kiểm tra |
| Cảnh báo thiếu dẫn chứng cần thiết                                  | 78         | 74         | −4                                           |

> **Giải thích hai lỗi văn phong/nội dung.**
>
> `answer omission` nghĩa là dẫn chứng đã có một thông tin quan trọng nhưng câu trả lời không nhắc đến. `repeated opening` nghĩa là nhiều câu trả lời bắt đầu bằng cùng một cụm từ, khiến toàn báo cáo bị lặp và thiếu tự nhiên; đây chủ yếu là lỗi văn phong, không đồng nghĩa với sai dữ liệu.

_Kết quả đo được_

### So sánh hai lần chạy Daewoong gần nhất

Cả hai lần chạy đều xử lý đủ 95 câu của cùng công ty và cùng năm. Lần chạy 10/08/2026 đọc thêm bảng số liệu trong phần định tính và nhận được nhiều dữ liệu định lượng hơn. Vì hệ thống kiểm tra nhiều vấn đề hơn trước, không nên dùng riêng số câu FAIL để kết luận bản mới tốt hay xấu.

#### Trước · 07/08/2026

run_20260807T075119574656Z

- Thời gian: 23,7 phút
- 2 Excel sheets
- Chưa có phần dữ liệu bảng riêng (`metric_context`) cho 23 câu cần số liệu
- Kích thước report: 119,8 KB

#### Sau · 10/08/2026

run_20260810T081824136413Z

- Thời gian: 26,8 phút
- 4 Excel sheets
- Đã xử lý 23 câu có bảng, nhận 216 dòng dữ liệu gốc
- Kích thước report: 179,5 KB

#### Bảng so sánh tổng hợp

| Nhóm                | Chỉ số                                                 | 07/08/2026 | 10/08/2026 | Đánh giá       |
| ------------------- | ------------------------------------------------------ | ---------- | ---------- | -------------- |
| Câu trả lời         | filled (đạt)                                           | 3          | 5          | +2             |
| Câu trả lời         | partial (có câu nhưng nguồn chưa đủ)                   | 64         | 55         | −9             |
| Câu trả lời         | needs_review (cần kiểm tra)                            | 26         | 33         | +7             |
| Câu trả lời         | missing (không có câu)                                 | 2          | 2          | 0              |
| Câu trả lời         | Câu có nội dung                                        | 83         | 82         | −1             |
| Kiểm tra chất lượng | PASS (đạt)                                             | 3          | 5          | +2             |
| Kiểm tra chất lượng | WARN (cảnh báo)                                        | 64         | 55         | −9             |
| Kiểm tra chất lượng | FAIL (không đạt)                                       | 28         | 35         | +7             |
| Kiểm tra chất lượng | Tổng warning                                           | 121        | 134        | +13            |
| Dẫn chứng           | SUFFICIENT (đủ)                                        | 6          | 6          | 0              |
| Dẫn chứng           | PARTIAL                                                | 78         | 67         | −11            |
| Dẫn chứng           | MISMATCH                                               | 8          | 9          | +1             |
| Dẫn chứng           | ERROR                                                  | 1          | 2          | +1             |
| Dẫn chứng           | Câu có bảng cần xem lại / độ tin cậy thấp / thiếu bảng | 0          | 9          | Kiểm soát mới  |
| Định lượng          | filled (đã điền)                                       | 70         | 104        | +34            |
| Định lượng          | needs_review                                           | 5          | 9          | +4             |
| Định lượng          | missing                                                | 135        | 97         | −38            |
| Định lượng          | Có giá trị                                             | 75         | 113        | +38            |
| Thời gian & độ dài  | Thời gian                                              | 23,7m      | 26,8m      | +3,1m (+13,1%) |
| Thời gian & độ dài  | Median độ dài, toàn bộ 95 câu                          | 556        | 549        | −7             |
| Thời gian & độ dài  | Số đoạn dẫn chứng dùng trung bình                      | 10,25      | 10,84      | +0,59          |

#### Phân bố QA

#### 07/08/2026

- PASS — 3

- WARN — 64

- FAIL — 28

#### 10/08/2026

- PASS — 5

- WARN — 55

- FAIL — 35

#### Chuyển trạng thái đáng chú ý

#### 5 câu cải thiện QA

Q006 FAIL→PASS · Q030 FAIL→WARN · Q035 FAIL→WARN · Q062 FAIL→WARN · Q065 WARN→PASS

#### 11 câu suy giảm QA

Q007 · Q011 · Q023 · Q043 · Q051 · Q055 · Q059 · Q063 · Q067 · Q089 · Q095

Đều chuyển WARN→FAIL.

#### Câu trống thay đổi

**Khôi phục:** Q062 **Mới trống:** Q049, Q059

> **Cách đọc đúng kết quả.**
>
> Lần chạy 10/08/2026 đọc được nhiều dữ liệu hơn và phát hiện được nhiều lỗi hơn, nhưng chưa tạo ra câu trả lời tốt hơn ở mọi mục. Số FAIL tăng một phần vì hệ thống mới kiểm tra cả bảng số liệu và lọc dẫn chứng chặt hơn. Dù vậy, 13 câu trống và 35 câu không đạt vẫn là vấn đề thật cần xử lý.

_Điểm còn hạn chế_

### Điểm còn yếu và nơi cần cải thiện

Các nhận xét dưới đây được rút ra từ tệp kết quả của lần chạy 10/08/2026 và việc đọc lại code hiện tại. Các vấn đề được xếp theo mức ảnh hưởng đến khả năng xuất báo cáo mà không cần người kiểm tra.

| Mức      | Điểm yếu                                                            | Dữ liệu quan sát                                                                                                                                                                       | Hướng cải thiện                                                                                                                                                 |
| -------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CAO**  | Kiểm tra số trong câu trả lời với bảng nguồn chưa ổn định.          | Trong 23 câu cần bảng: 21 câu không đạt, 2 câu cần xem lại; số lỗi “không tìm thấy số tương ứng trong nguồn” tăng từ 57 lên 69.                                                        | Đưa số và đơn vị về cùng cách viết trước khi so sánh; đối chiếu theo đúng ô và ý nghĩa của dòng bảng, không so khớp nguyên chuỗi chữ.                           |
| **CAO**  | API chưa cung cấp đủ dẫn chứng.                                     | Chỉ 6/95 câu có dẫn chứng đầy đủ; 74 câu được cảnh báo thiếu nguồn cần thiết; 8/23 câu cần bảng nhưng không tìm thấy bảng.                                                             | Cải thiện hệ thống tìm kiếm RAG/API theo từng ý bắt buộc của câu hỏi và bổ sung tìm bảng cho 8 câu còn thiếu. Không nên nới lỏng tiêu chuẩn chỉ để giảm số lỗi. |
| **CAO**  | Bước lọc dẫn chứng có thể lỗi và làm mất toàn bộ câu trả lời.       | Số lỗi xử lý tăng từ 1 lên 2; Q049 và Q059 mới bị trống; 9 câu bị đánh dấu dẫn chứng không khớp.                                                                                       | Chia yêu cầu lớn thành nhóm nhỏ, thử lại riêng nhóm bị lỗi và dùng kiểm tra bằng quy tắc cố định khi API đã gắn đúng mã Q.                                      |
| **VỪA**  | Tiêu chuẩn kiểm tra chưa cân bằng giữa đủ chi tiết và ngắn gọn.     | Số câu bỏ sót ý giảm từ 5 xuống 3, nhưng cảnh báo câu ngắn tăng từ 23 lên 28. AI đánh giá nội dung đạt ở 78 câu, trong khi kết quả chung vẫn có 35 câu không đạt do các kiểm tra khác. | Tách riêng ba loại: nguồn bị thiếu, câu trả lời bỏ sót ý và bảng trình bày sai. Chỉ yêu cầu AI viết lại khi dữ liệu hiện có đủ để sửa.                          |
| **VỪA**  | Thời gian chạy tăng khi thêm bước kiểm tra.                         | Thời gian tăng từ 23,7 lên 26,8 phút (+13,1%); 84/95 câu được sinh lại.                                                                                                                | Lưu dấu nhận biết dữ liệu và cấu hình của từng câu, bỏ qua câu không thay đổi và chỉ kiểm tra lại phần câu trả lời hoặc bảng vừa đổi.                           |
| **THẤP** | Có nhật ký nhưng chưa có màn hình theo dõi xu hướng nhiều lần chạy. | Hệ thống đã có log, cấu hình LangSmith và Temporal, nhưng việc so sánh vẫn phải tổng hợp nhiều tệp kết quả.                                                                            | Tạo một tệp số liệu tổng hợp chuẩn cho mỗi lần chạy và màn hình so sánh theo công ty, mô hình AI và phiên bản API.                                              |

#### Kết quả chi tiết của 23 câu cần bảng số liệu

**23**

câu được xác định là cần bảng số liệu; mã trong code là `metric_expected`.

**15**

câu tìm thấy bảng, 8 câu không tìm thấy.

**110/118**

dòng kết quả chính được bước lọc dẫn chứng chấp nhận.

**0 đạt**

21 câu không đạt, 2 câu cần xem lại: kiểm tra câu có bảng là ưu tiên cao nhất.

15 câu tìm thấy bảng: Q007, Q019, Q027, Q031, Q035, Q039, Q047, Q059, Q063, Q067, Q071, Q075, Q079, Q087, Q091. 8 câu chưa tìm thấy: Q011, Q015, Q023, Q043, Q051, Q055, Q083, Q095.

_Giải thích bằng lời đơn giản_

### Chú thích thuật ngữ và mã kỹ thuật

Báo cáo đã ưu tiên dùng lời dễ hiểu. Tuy nhiên, một số tên công nghệ, tên cột và trạng thái cần giữ nguyên để đối chiếu với code và tệp kết quả. Danh sách dưới đây giải thích chúng theo cách ngắn gọn.

- **LangGraph:** Thư viện giúp sắp xếp các bước xử lý AI thành một luồng rõ ràng, có nhánh rẽ, vòng kiểm tra lại và trạng thái được lưu giữa các bước.
- **Graph / StateGraph:** Sơ đồ mô tả bước nào chạy trước, bước nào chạy sau và khi gặp lỗi thì đi sang nhánh nào. “State” là dữ liệu đang được truyền giữa các bước.
- **Node:** Một bước cụ thể trong luồng, ví dụ nhận dữ liệu, kiểm tra dẫn chứng hoặc xuất Excel.
- **Run:** Một lần chạy báo cáo từ đầu đến cuối cho một công ty và một năm. Mỗi lần chạy có thư mục kết quả riêng.
- **Agent:** Một vai trò có trách nhiệm rõ ràng trong hệ thống, như vai trò nhận dữ liệu, kiểm tra dẫn chứng hoặc AI chuyên viết về an toàn lao động.
- **AgentSkill / Skill:** Một chức năng nhỏ mà Agent sử dụng, ví dụ chia đoạn dẫn chứng, kiểm tra câu hoặc ghi tệp kết quả.
- **LLM:** Mô hình ngôn ngữ lớn, tức AI có khả năng đọc và viết văn bản. Trong dự án, LLM viết câu định tính và hỗ trợ đánh giá; không dùng để điền 210 số liệu định lượng.
- **Writer / ESG expert writer:** AI chuyên viết câu trả lời. Hệ thống chia 24 Writer theo chủ đề để câu về khí hậu, nhân quyền, quản trị... được giao đúng chuyên môn.
- **Router / Routing:** Bước chọn đúng AI chuyên viết cho từng câu hỏi. Mỗi câu chỉ được giao cho một Writer.
- **Evidence:** Dữ liệu dẫn chứng dùng để viết câu trả lời, có thể là đoạn văn, dòng bảng, số liệu, tên nguồn hoặc vị trí trong tài liệu.
- **Fragment:** Một phần nhỏ được tách ra từ đoạn dẫn chứng dài để hệ thống đánh giá chính xác hơn. Nội dung gốc không được viết lại.
- **Narrative:** Dẫn chứng dạng đoạn mô tả bằng lời, khác với dữ liệu dạng dòng và cột trong bảng.
- **Metric:** Câu hỏi cần số liệu hoặc bảng, ví dụ số người, tỷ lệ, lượng phát thải hoặc kết quả theo năm.
- **Primary row / Denominator / Scope variant:** **Primary row** là dòng kết quả chính cần đưa vào trả lời. **Denominator** là dòng tổng dùng để tính tỷ lệ. **Scope variant** là số liệu có phạm vi khác, ví dụ công ty mẹ thay vì toàn tập đoàn.
- **Relevance gate:** Bước lọc xem một đoạn dẫn chứng có đúng chủ đề câu hỏi hay không. AI chỉ chấp nhận hoặc loại bỏ, không sửa nội dung dẫn chứng.
- **Coverage:** Mức độ dẫn chứng đáp ứng các ý mà câu hỏi yêu cầu. Coverage thấp nghĩa là có dữ liệu liên quan nhưng còn thiếu một hoặc nhiều ý quan trọng.
- **Prompt:** Nội dung hướng dẫn gửi cho AI, gồm câu hỏi, dẫn chứng được chọn, quy tắc văn phong và điều cấm.
- **Deterministic check:** Kiểm tra bằng quy tắc cố định trong code, cho cùng dữ liệu sẽ luôn cho cùng kết quả; ví dụ kiểm tra câu trống, độ dài hoặc số có xuất hiện trong nguồn.
- **LLM Judge:** AI đóng vai trò người đánh giá, kiểm tra câu có bịa thông tin, bỏ sót ý, mâu thuẫn hoặc dùng sai dẫn chứng hay không.
- **QA:** Kiểm tra chất lượng. **PASS**: đạt; **WARN**: có cảnh báo nhưng vẫn có thể dùng sau khi xem lại; **FAIL**: không đạt; **FATAL**: lỗi nghiêm trọng làm quy trình không thể hoàn thành đúng.
- **Answer status:** **filled**: câu và dẫn chứng đạt; **partial**: có câu trả lời nhưng dẫn chứng chưa đủ; **needs_review**: cần người kiểm tra; **missing**: không có câu trả lời.
- **Evidence status:** **SUFFICIENT**: dẫn chứng đủ; **PARTIAL**: còn thiếu; **MISMATCH**: sai chủ đề; **NONE**: không có; **ERROR**: bước xử lý dẫn chứng bị lỗi.
- **Rewrite / Polish:** **Rewrite** là viết lại câu chưa đạt. **Polish** là chỉnh văn phong cho tự nhiên và thống nhất, không được thay đổi số liệu hoặc ý chính.
- **Checkpoint / Resume:** **Checkpoint** là bản lưu tạm sau khi xử lý xong từng phần. **Resume** là tiếp tục từ bản lưu đó thay vì chạy lại từ đầu.
- **Retry / Timeout:** **Retry** là tự thử lại khi lỗi tạm thời. **Timeout** là giới hạn thời gian; quá thời gian thì bước đó dừng để tránh treo toàn hệ thống.
- **API / JSON:** **API** là cổng để hai hệ thống trao đổi dữ liệu tự động. **JSON** là định dạng văn bản có cấu trúc dùng để gửi và lưu dữ liệu.
- **RAG:** Cách tìm đoạn hoặc bảng liên quan trong kho tài liệu rồi gửi phần tìm được cho AI trả lời. RAG tốt giúp AI có đúng nguồn trước khi viết.
- **Audit:** Khả năng truy lại câu trả lời đã dùng nguồn nào, dòng nào và qua bước kiểm tra nào để người đọc có thể đối chiếu.
- **LangSmith:** Công cụ theo dõi các lần gọi AI, nội dung vào/ra, thời gian và lỗi để tìm nguyên nhân khi kết quả có vấn đề.
- **Temporal:** Công cụ điều phối công việc chạy lâu, giúp quản lý hàng đợi, thử lại và tiếp tục quy trình khi dịch vụ bị gián đoạn. Trong dự án, Temporal là tùy chọn.
- **Manifest:** Tệp danh sách mô tả các Agent, mô hình AI, nội dung hướng dẫn và Skill mà từng Agent được phép dùng.

_Đánh giá cuối_

### Kết luận

> **Kiến trúc đã đúng hướng; chất lượng tự động xuất bản chưa đạt.**
>
> Hệ thống hiện có luồng xử lý rõ ràng, 34 vai trò, 31 chức năng nhỏ, dữ liệu tách riêng theo câu, kiểm tra hai lớp, bản lưu tạm và bảng đối chiếu nguồn. Lần chạy 10/08/2026 cho thấy hệ thống đã đọc được bảng trong câu định tính và điền được nhiều số liệu định lượng hơn. Tuy nhiên, 35 câu không đạt, 13 câu trống và 21/23 câu có bảng không đạt cho thấy vẫn cần người kiểm tra trước khi phát hành.

#### Kết luận so sánh trước và sau

#### Đã cải thiện rõ

Số mục định lượng có giá trị tăng 75→113; thêm xử lý cho 23 câu cần bảng; Excel có sheet đối chiếu; lỗi bỏ sót ý và mở đầu lặp lại đã giảm.

#### Cải thiện một phần

Số câu đạt tăng 3→5 và cảnh báo thiếu nguồn giảm, nhưng hệ thống chủ yếu phát hiện vấn đề tốt hơn chứ chưa sửa được hết vấn đề.

#### Chưa cải thiện

Số câu không đạt tăng 28→35, câu có nội dung giảm 83→82, thời gian tăng 13,1% và chưa có câu cần bảng nào đạt hoàn toàn.

#### Ba ưu tiên có tác động cao nhất

| #   | Ưu tiên                                                                                         | Kết quả kỳ vọng                                                                                           |
| --- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| 1   | Đưa số và đơn vị về cùng cách viết, rồi kiểm tra theo đúng dòng và ô trong bảng nguồn.          | Giảm phần lớn 69 lỗi đối chiếu số và giúp các câu cần bảng chuyển từ không đạt sang cần xem lại hoặc đạt. |
| 2   | Cải thiện hệ thống tìm dẫn chứng cho 8 câu chưa tìm thấy bảng và các ý bắt buộc còn thiếu.      | Giảm cảnh báo thiếu nguồn mà không cần hạ thấp tiêu chuẩn kiểm tra.                                       |
| 3   | Làm bước lọc dẫn chứng ít bị lỗi hơn và chỉ yêu cầu AI viết lại những câu có đủ dữ liệu để sửa. | Giảm câu trống, lỗi lọc dẫn chứng và thời gian chạy.                                                      |

> **Phán quyết cuối.**
>
> Bản 10/08/2026 tốt hơn về cách tổ chức dữ liệu, số lượng mục định lượng có giá trị và khả năng truy lại nguồn; chất lượng câu trả lời định tính chưa tốt hơn đồng đều. Cách vận hành phù hợp hiện tại là “AI viết bản đầu, hệ thống kiểm tra, con người duyệt lại”, chưa nên tự động phát hành hoàn toàn.

Nguồn: hai báo cáo HTML tham chiếu, danh sách vai trò, sơ đồ xử lý hiện tại và các tệp kết quả Daewoong ngày 07/08/2026 & 10/08/2026.

---

# 한국어 버전

아키텍처 및 운영 보고서 · 대웅제약 ESG 2025 · 2026/08/10

## ESG LangGraph: 프로젝트 개요 및 최근 두 실행 비교

V3

시스템의 작동 방식, 역할 분담, 2026년 8월 7일과 2026년 8월 10일 대웅제약 실행 결과를 설명합니다. 더 많은 데이터를 읽게 된 것과 최종 답변 품질이 실제로 향상된 것을 구분해 평가합니다.

[↗ Google Drive에서 최신 대웅제약 보고서 열기](https://docs.google.com/spreadsheets/d/1-QwR51i7RMo4wghsE8pT-fRYTO1TIqODWJr6djOsQUI/edit?usp=drive_web&ouid=112413599409010031174)

- **95 + 210** — 하나의 보고서에 포함되는 정성·정량 항목

- **34** — 역할: 공통 역할 10개 + ESG 전문 작성 AI 24개

- **31** — 재시도, 시간 제한, 기록 기능이 있는 세부 기능

- **75 → 113** — 값이 있는 정량 항목, 38개 증가

_시스템 전체 보기_

### 프로젝트 개요

회사·연도별 ESG 보고서를 생성합니다. 데이터는 JSON 파일 또는 다른 데이터 시스템과 연결하는 API를 통해 받을 수 있으며 현재는 API를 사용합니다. LangGraph는 95개 정성 문항의 처리 순서를 관리합니다. 210개 정량 항목은 AI가 다시 작성하지 않고 값을 직접 가져와 채웁니다.

**API**

회사와 보고 연도에 맞는 정성 근거와 정량 수치를 받습니다.

**2개 흐름**

하나는 전체 보고서를 관리하고 다른 하나는 정성 문항별 처리를 담당합니다.

**문항별 분리**

Qxxx는 해당 문항의 근거만 사용하여 95개 문항 간 데이터 혼합을 막습니다.

**Excel**

답변, 검사 결과, 수치 및 출처 대조표를 출력합니다.

#### 입력과 출력

#### 회사별 입력

- 회사명, `company_id`, 업종, 규모 및 보고 연도.
- Q001-Q095별 narrative 및 metric evidence.
- 210개 template용 정량 API 답변.
- 업종·규모별 template rule, item contract 및 writer profile.

#### 실행별 출력

- 정성 답변 JSON, QA checklist 및 매핑된 정량 데이터.
- timeout/quota 오류 시 재개 가능한 item별 partial checkpoint.
- 최종 Excel은 본 보고서, 정량(`Quantitative`), 정성 수치 표(`Qualitative Metrics`), 출처 대조 데이터(`Metric Evidence Audit`) 4개 sheet로 구성됩니다.
- 단계, 기능, 답변별 기록을 남깁니다. LangSmith는 AI 호출 상세 추적, Temporal은 활성화 시 장시간 작업 조정을 지원합니다.

> **종합 평가.**
>
> 현재 책임 구분은 명확하고 출처를 다시 확인할 수 있습니다. 핵심 문제는 처리 흐름 부족이 아니라 API 근거 부족, 표 답변 수치 대조의 불안정, 검사 후 재작성 시간입니다.

_처리 구조_

### 현재 처리 흐름

보고서 흐름은 데이터 수신부터 Excel 출력까지 한 번의 실행 전체를 관리합니다. `generate_qualitative`(정성 답변 생성) 단계에서 95개 문항은 같은 처리 틀을 사용하지만 각 문항의 데이터, 규칙, 전문 작성 AI는 분리됩니다. 따라서 다른 문항의 데이터가 섞이지 않습니다.

#### 전체 보고서 흐름 · 6단계

- **01 · 실행 준비** — `initialize_run`: 결과 폴더를 만들고 설정, 업종, 보고서 양식을 읽습니다.

- **02 · 데이터 수신** — `load_company_input`: 해당 회사·연도의 API 또는 파일 데이터를 읽습니다.

- **03 · 데이터 정리** — `normalize_evidence`: 정성·정량 데이터를 공통 구조로 정리합니다.

- **04 · 95개 답변 작성** — `generate_qualitative`: 문항별 처리, 전체 검사, 문체 정리를 수행합니다.

- **05 · 정량 210개 입력** — `map_quantitative`: AI 작성 없이 값을 직접 채웁니다.

- **06 · 결과 출력** — `write_outputs`: 데이터, 검사 결과, 임시 저장본, 최종 Excel을 기록합니다.

#### 정성 문항 하나의 처리 흐름 · 기술 단계 17개를 이해하기 쉬운 10개 그룹으로 정리

- **1 · 문항 규칙 읽기** — 각 Qxxx에는 데이터, 작성, 검사에 대한 개별 규칙이 있습니다.

- **2 · 정확한 데이터 선택** — 회사, 연도, 문항 번호를 확인하고 설명문과 수치 행을 나눕니다.

- **3 · 근거 분할** — 긴 근거를 읽기 쉬운 단위로 나누되 원문 내용은 바꾸지 않습니다.

- **4 · 관련 내용 선별** — AI는 질문과의 관련 여부만 판단하며 근거를 다시 쓰지 않습니다.

- **5 · 데이터 충분성 확인** — 근거가 충분한지 확인하고 작성 AI에 보낼 핵심 내용을 고릅니다.

- **6 · ESG 전문가 선택** — 문항을 24개 주제별 전문 작성 AI 중 하나에 배정합니다.

- **7 · 초안 작성** — 승인된 데이터만 사용해 한국어 초안을 작성합니다.

- **8 · 표현 형식 정리** — 평가 전에 언어, 깨진 문자, 표현 형식을 정리합니다.

- **9 · 이중 검사** — 고정 규칙은 수치·형식을 검사하고 AI는 허위 내용, 누락, 모순을 검사합니다.

- **10 · 재작성 또는 종료** — 미달 답변은 다시 작성·검사하고 근거 부족·불일치 문항은 명확히 표시해 종료합니다.

#### 표 수치가 있는 정성 문항 처리 방식

#### 1 · 표 행 읽기

API V3가 표 행을 전달합니다. 시스템은 핵심 결과 행, 비율 계산용 전체 행, 범위가 다른 행을 구분하고 단위와 표 그룹을 유지합니다.

#### 2 · AI 입력 준비

관련 있는 핵심 결과 행을 같은 표와 대상별로 묶어 AI 지시문에 넣습니다. 긴 설명문은 핵심 내용만 선택합니다.

#### 3 · AI는 설명, 시스템은 표 생성

AI는 설명문을 작성합니다. Excel 표는 구조화 데이터에서 직접 생성하고 AI가 수치를 기억하거나 임의 배열하지 않으며 별도 sheet에 대조 데이터를 남깁니다.

_책임 분담_

### 시스템의 역할과 기능

**Agent**는 데이터 수신, 근거 검사, 답변 작성처럼 책임이 분명한 AI 또는 처리 역할입니다. **AgentSkill**은 근거 분할, 답변 검사, Excel 출력처럼 각 역할이 사용하는 작은 기능입니다. 각 기능에는 시간 제한, 오류 재시도, 추적 기록이 있습니다. manifest 파일은 각 역할이 사용할 AI 모델, 지시문, 기능을 정리한 목록입니다.

**10**

전체 과정을 관리하는 공통 역할.

**24**

24개 ESG 주제별 전문 작성 AI, 95개 문항 전체 담당.

**31**

전체 흐름 변경 없이 개별 검사·교체 가능한 작은 기능.

#### 10개 공통 역할

| Agent                           | 주요 역할                                              | Skill 그룹   |
| ------------------------------- | ------------------------------------------------------ | ------------ |
| `report_orchestrator_agent`     | run 초기화, static config 로드, sector 결정.           | Bootstrap    |
| `input_data_agent`              | API/file 읽기 및 회사 데이터 정규화.                   | Input        |
| `template_policy_agent`         | 업종·규모·item별 template rule 선택.                   | Policy       |
| `evidence_retrieval_agent`      | scope, segment, relevance, coverage 및 Evidence focus. | Evidence     |
| `qualitative_item_policy_agent` | Q001-Q095별 contract 로드·검증.                        | Contract     |
| `esg_writer_router_agent`       | 각 item을 정확히 하나의 expert writer에 할당.          | Routing      |
| `qualitative_reviewer_agent`    | 고정 규칙 검사, AI 검사 및 결과 병합.                  | 검사         |
| `style_editor_agent`            | batch review, style rewrite, final polish 및 재검증.   | Style        |
| `quantitative_mapper_agent`     | LLM 없이 210개 정량 항목 매핑.                         | Quantitative |
| `excel_report_agent`            | 결과 파일, 임시 저장본, 최종 Excel 기록.               | 파일 출력    |

#### 24개 ESG 주제별 전문 작성 AI

각 전문 작성 AI는 특정 주제와 문항 목록을 담당합니다. 각 AI의 설명에는 필요한 전문성, 우선 작성 내용, 피해야 할 오류가 명시되어 있습니다. 모두 같은 근거 사용 규칙과 품질 검사를 따릅니다.

- **ESG 경영** — Q001-Q003

- **산업안전보건** — Q004-Q007

- **노동·인권** — Q008-Q011

- **제품안전** — Q012-Q015

- **정보보호** — Q016-Q019

- **환경경영** — Q020-Q023

- **윤리경영** — Q024-Q027

- **기후행동** — Q028-Q031

- **자원순환** — Q032-Q035

- **물 관리** — Q036-Q039

- **생물다양성** — Q040-Q043

- **오염·배출** — Q044-Q047

- **지속가능 제품** — Q048-Q051

- **제품책임** — Q052-Q055

- **인적자본** — Q056-Q059

- **다양성·포용성** — Q060-Q063

- **책임 있는 공급망** — Q064-Q067

- **지역사회 영향** — Q068-Q071

- **위원회 거버넌스** — Q072-Q075

- **이사회 구성** — Q076-Q079

- **ESG 운영체계** — Q080-Q083

- **컴플라이언스** — Q084-Q087

- **소유구조·운영** — Q088-Q091

- **이해관계자 소통** — Q092-Q095

#### 업무 그룹별 31개 세부 기능

| 업무 그룹               | 기능 수 | 주요 업무                                                        |
| ----------------------- | ------- | ---------------------------------------------------------------- |
| 초기화 & 데이터 수신    | 6       | 설정, 업종, 양식, 회사 데이터 읽기; 데이터 정리 및 규칙 선택     |
| 근거 & 문항별 규칙      | 8       | 정리, 문항 매칭, 분할, 관련성 필터, 충분성 평가, 규칙 검사       |
| 전문가 선택 & 답변 작성 | 9       | 전문 작성 AI 선택, 4개 그룹별 내용 준비, 초안, 재작성, 형식 정리 |
| 검사 & 문체             | 6       | 규칙 검사, AI 평가, 결과 병합, 전체 검사, 재작성, 최종 문체 정리 |
| 정량 & 파일 출력        | 2       | 210개 수치 입력, JSON·Excel 기록                                 |

code의 기능 등록 목록(`build_default_skill_registry`)과 직접 대조한 총 기능 수는 31개입니다.

_구현한 변경 사항_

### 구현된 개선 사항

이전 버전보다 문항별 근거 분리가 강화되었고, 정성 항목의 표 수치를 읽을 수 있으며, 출처 대조표를 추가하고 실행 중단 시 저장된 결과에서 이어갈 수 있습니다.

#### 1 · 근거 혼합 방지

API 사용 시 회사, 연도, 문항 번호를 확인하고 해당 Qxxx 데이터만 처리합니다. 95개 전체 데이터에서 다시 검색하지 않습니다.

#### 2 · 원문 내용 보존

긴 설명은 나누지만 다시 쓰지 않습니다. API 원본은 대조용으로 보존하고 분할본만 AI 입력으로 사용합니다.

#### 3 · AI 설명과 고정 표 결합

AI는 설명을 작성하고 수치 표는 원천 데이터에서 직접 만듭니다. 표가 필요한 23개 문항을 인식하고 출처 확인용 sheet를 추가했습니다.

#### 4 · 이중 검사

고정 규칙은 형식과 수치를 검사하고 AI는 허위 내용, 누락, 모순을 검사합니다. 수정 답변은 다시 검사합니다.

#### 5 · 문항별 개별 규칙

Q001-Q095별 요구사항으로 한 문항의 수정이 다른 문항에 미치는 영향을 줄입니다. AI는 없는 데이터를 임의로 설명하지 않습니다.

#### 6 · 오류 후 이어서 실행

기능별 대기 시간과 재시도 횟수가 있습니다. 문항별 결과를 순차 저장하고 기록에서 오류 단계와 문항을 확인할 수 있습니다.

#### 2026년 8월 10일 실행의 측정 개선

| 지표                                                    | 07/08/2026 | 10/08/2026 | 평가                                |
| ------------------------------------------------------- | ---------- | ---------- | ----------------------------------- |
| 값이 있는 정량 항목                                     | 75         | 113        | +38 (+50,7%)                        |
| 값이 입력된 정량 항목, 상태 code `filled`               | 70         | 104        | +34                                 |
| 인식된 표 수치 문항                                     | 0          | 23         | 신규 기능                           |
| 승인된 표의 핵심 결과 행(`primary Metric row`)          | -          | 110/118    | 93,2%                               |
| 품질 검사 통과 문항(`QA PASS`)                          | 3          | 5          | +2                                  |
| AI 내용 평가에서 미달된 문항(`LLM Judge failed`)        | 7          | 4          | −3                                  |
| 근거에 있는 중요 내용을 빠뜨린 문항(`answer omission`)  | 5          | 3          | −2                                  |
| 다른 답변과 시작 문구가 반복된 문항(`repeated opening`) | 2          | 0          | 검사 목록에서 더 이상 발견되지 않음 |
| 필요 근거 부족 경고                                     | 78         | 74         | −4                                  |

> **두 가지 내용·문체 오류 설명.**
>
> `answer omission`은 근거에 중요한 정보가 있는데 답변에서 빠뜨린 경우입니다. `repeated opening`은 여러 답변이 같은 문구로 시작해 보고서가 반복적이고 부자연스러운 경우이며, 주로 문체 문제로 데이터 오류와는 다릅니다.

_측정 결과_

### 최근 대웅제약 두 실행 비교

두 실행 모두 같은 회사·연도의 95개 문항을 처리했습니다. 2026년 8월 10일 실행은 정성 항목의 표를 추가로 읽고 더 많은 정량 데이터를 받았습니다. 이전보다 더 많은 문제를 검사하므로 FAIL 수만으로 신규 버전의 품질을 판단하면 안 됩니다.

#### 이전 · 07/08/2026

run_20260807T075119574656Z

- 실행 시간: 23.7분
- Excel sheet 2개
- 수치가 필요한 23개 문항의 표 데이터(`metric_context`) 미지원
- report 크기: 119.8 KB

#### 이후 · 10/08/2026

run_20260810T081824136413Z

- 실행 시간: 26.8분
- Excel sheet 4개
- 표가 있는 23개 문항, 원본 데이터 행 216개 처리
- report 크기: 179.5 KB

#### 종합 비교표

| 구분        | 지표                                      | 07/08/2026 | 10/08/2026 | 평가           |
| ----------- | ----------------------------------------- | ---------- | ---------- | -------------- |
| 답변        | filled (충족)                             | 3          | 5          | +2             |
| 답변        | partial (답변은 있으나 근거 부족)         | 64         | 55         | −9             |
| 답변        | needs_review (검토 필요)                  | 26         | 33         | +7             |
| 답변        | missing (답변 없음)                       | 2          | 2          | 0              |
| 답변        | 내용이 있는 답변                          | 83         | 82         | −1             |
| 품질 검사   | PASS (통과)                               | 3          | 5          | +2             |
| 품질 검사   | WARN (경고)                               | 64         | 55         | −9             |
| 품질 검사   | FAIL (미달)                               | 28         | 35         | +7             |
| 품질 검사   | 전체 warning                              | 121        | 134        | +13            |
| 근거        | SUFFICIENT (충분)                         | 6          | 6          | 0              |
| 근거        | PARTIAL                                   | 78         | 67         | −11            |
| 근거        | MISMATCH                                  | 8          | 9          | +1             |
| 근거        | ERROR                                     | 1          | 2          | +1             |
| 근거        | 표 문항 검토 필요 / 낮은 신뢰도 / 표 누락 | 0          | 9          | 신규 통제      |
| 정량        | filled (입력 완료)                        | 70         | 104        | +34            |
| 정량        | needs_review                              | 5          | 9          | +4             |
| 정량        | missing                                   | 135        | 97         | −38            |
| 정량        | 값 있음                                   | 75         | 113        | +38            |
| 시간 & 길이 | 실행 시간                                 | 23,7m      | 26,8m      | +3,1m (+13,1%) |
| 시간 & 길이 | 95개 전체 답변 길이 중앙값                | 556        | 549        | −7             |
| 시간 & 길이 | 평균 사용 근거 조각 수                    | 10,25      | 10,84      | +0,59          |

#### QA 분포

#### 07/08/2026

- PASS — 3

- WARN — 64

- FAIL — 28

#### 10/08/2026

- PASS — 5

- WARN — 55

- FAIL — 35

#### 주요 상태 전환

#### QA 개선 5개

Q006 FAIL→PASS · Q030 FAIL→WARN · Q035 FAIL→WARN · Q062 FAIL→WARN · Q065 WARN→PASS

#### QA 악화 11개

Q007 · Q011 · Q023 · Q043 · Q051 · Q055 · Q059 · Q063 · Q067 · Q089 · Q095

모두 WARN→FAIL 전환.

#### 빈 답변 변화

**복구:** Q062 **신규 빈 답변:** Q049, Q059

> **결과 해석 방법.**
>
> 2026년 8월 10일 실행은 더 많은 데이터를 읽고 더 많은 오류를 발견했지만 모든 문항의 답변이 좋아진 것은 아닙니다. 표 수치 검사와 근거 필터가 강화되어 FAIL이 일부 증가했습니다. 그러나 빈 답변 13개와 미달 35개는 실제 해결 과제입니다.

_남아 있는 한계_

### 잔여 한계와 개선 지점

아래 내용은 2026년 8월 10일 실행 결과 파일과 현재 code 검토를 바탕으로 정리했습니다. 사람의 확인 없이 보고서를 내보낼 때 미치는 영향이 큰 순서입니다.

| 수준     | 한계                                                    | 관찰 데이터                                                                                                                                                   | 개선 방향                                                                                                                                |
| -------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **CAO**  | 답변 수치와 원본 표의 대조가 불안정합니다.              | 표가 필요한 23개 문항 중 21개 미달, 2개 검토 필요; 원본에서 대응 수치를 찾지 못한 오류가 57건에서 69건으로 증가했습니다.                                      | 비교 전에 숫자와 단위 표현을 통일하고 문자열 전체가 아닌 표의 셀과 행 의미를 기준으로 대조합니다.                                        |
| **CAO**  | API 근거가 충분하지 않습니다.                           | 근거가 충분한 문항은 6/95개, 필요한 출처 부족 경고는 74개이며 표가 필요한 23개 중 8개는 표를 찾지 못했습니다.                                                 | 문항의 필수 내용별 RAG/API 검색을 개선하고 8개 누락 문항의 표 검색을 보강합니다. 오류 수를 줄이기 위해 검사 기준을 완화해서는 안 됩니다. |
| **CAO**  | 근거 필터 오류가 전체 답변 손실로 이어질 수 있습니다.   | 처리 오류가 1건에서 2건으로 증가했고 Q049·Q059가 새로 비었으며 9개 문항의 근거가 불일치로 표시되었습니다.                                                     | 큰 요청을 작은 그룹으로 나누고 오류 그룹만 재시도하며 API의 Q 매핑이 정확할 때는 고정 규칙 검사를 보조로 사용합니다.                     |
| **VỪA**  | 검사 기준이 상세성과 간결성 사이에서 균형이 부족합니다. | 내용 누락 문항은 5개에서 3개로 줄었지만 짧은 답변 경고는 23개에서 28개로 늘었습니다. AI 내용 평가는 78개가 통과했지만 다른 검사까지 합치면 35개가 미달입니다. | 출처 부족, 답변 내용 누락, 표 형식 오류를 분리하고 현재 데이터로 수정 가능한 경우에만 AI 재작성을 요청합니다.                            |
| **VỪA**  | 검사 단계 추가로 실행 시간이 늘었습니다.                | 실행 시간이 23.7분에서 26.8분으로 13.1% 증가했고 95개 중 84개 답변이 다시 생성되었습니다.                                                                     | 문항별 데이터·설정 식별값을 저장하고 변경 없는 문항은 건너뛰며 수정된 답변이나 표만 다시 검사합니다.                                     |
| **THẤP** | 기록은 있으나 여러 실행의 추세 화면은 없습니다.         | log, LangSmith 설정, Temporal은 있으나 비교하려면 여러 결과 파일을 모아야 합니다.                                                                             | 실행마다 표준 요약 지표 파일을 만들고 회사, AI 모델, API 버전별 비교 화면을 구성합니다.                                                  |

#### 표 수치가 필요한 23개 문항의 상세 결과

**23**

표 수치가 필요하다고 판단된 문항; code 표시는 `metric_expected`.

**15**

표 발견 문항, 8개는 미발견.

**110/118**

근거 필터가 승인한 핵심 결과 행.

**통과 0개**

미달 21개, 검토 필요 2개: 표 문항 검사가 최우선 과제입니다.

표 발견 15개: Q007, Q019, Q027, Q031, Q035, Q039, Q047, Q059, Q063, Q067, Q071, Q075, Q079, Q087, Q091. 미발견 8개: Q011, Q015, Q023, Q043, Q051, Q055, Q083, Q095.

_쉬운 용어 설명_

### 기술 용어와 code 표기 설명

보고서는 쉬운 표현을 우선 사용했습니다. 다만 code와 결과 파일을 대조하기 위해 일부 기술명, 열 이름, 상태값은 원문을 유지합니다. 아래에서 간단히 설명합니다.

- **LangGraph:** AI 처리 단계를 순서, 분기, 재검사 반복, 단계 간 저장 상태로 구성하는 라이브러리입니다.
- **Graph / StateGraph:** 어떤 단계가 먼저·나중에 실행되고 오류 시 어느 경로로 가는지 나타내는 처리도입니다. State는 단계 사이에 전달되는 데이터입니다.
- **Node:** 데이터 수신, 근거 검사, Excel 출력처럼 흐름 안의 개별 처리 단계입니다.
- **Run:** 한 회사·연도의 보고서를 처음부터 끝까지 처리한 한 번의 실행입니다. 실행마다 결과 폴더가 따로 있습니다.
- **Agent:** 데이터 수신, 근거 검사, 산업안전 전문 작성 AI처럼 책임이 명확한 역할입니다.
- **AgentSkill / Skill:** 근거 분할, 답변 검사, 결과 파일 저장처럼 Agent가 사용하는 작은 기능입니다.
- **LLM:** 문장을 읽고 쓰는 대규모 언어 모델입니다. 정성 답변 작성과 평가에 사용하며 210개 정량 값 입력에는 사용하지 않습니다.
- **Writer / ESG expert writer:** 답변을 작성하는 AI입니다. 기후, 인권, 거버넌스 등 24개 주제별 전문 Writer로 나뉩니다.
- **Router / Routing:** 문항에 맞는 전문 작성 AI를 선택하는 단계이며 각 문항은 하나의 Writer에만 배정됩니다.
- **Evidence:** 답변 작성에 사용하는 근거 데이터로 문단, 표 행, 수치, 출처명, 문서 위치 등이 포함됩니다.
- **Fragment:** 긴 근거를 더 정확히 평가하기 위해 나눈 작은 단위이며 원문 내용은 다시 쓰지 않습니다.
- **Narrative:** 표의 행·열 데이터와 달리 문장이나 문단으로 설명된 근거입니다.
- **Metric:** 인원, 비율, 배출량, 연도별 실적처럼 수치나 표가 필요한 문항입니다.
- **Primary row / Denominator / Scope variant:** **Primary row**는 답변에 사용할 핵심 결과 행, **Denominator**는 비율 계산용 전체 행, **Scope variant**는 본사·연결 기준처럼 범위가 다른 수치입니다.
- **Relevance gate:** 근거가 질문 주제와 맞는지 판단하는 필터 단계입니다. AI는 승인·제외만 하고 근거 내용은 수정하지 않습니다.
- **Coverage:** 근거가 질문의 요구 내용을 얼마나 충족하는지 나타냅니다. 낮으면 관련 데이터는 있지만 중요한 내용이 부족하다는 뜻입니다.
- **Prompt:** 질문, 선택된 근거, 문체 규칙, 금지 사항을 포함해 AI에 보내는 지시문입니다.
- **Deterministic check:** 같은 데이터에 항상 같은 결과를 내는 code 고정 규칙 검사입니다. 빈 답변, 길이, 원본 수치 존재 여부 등을 검사합니다.
- **LLM Judge:** 답변의 허위 내용, 누락, 모순, 근거 오용을 검사하는 평가용 AI입니다.
- **QA:** 품질 검사입니다. **PASS**: 통과, **WARN**: 확인이 필요한 경고, **FAIL**: 미달, **FATAL**: 정상 완료를 막는 심각한 오류입니다.
- **Answer status:** **filled**: 답변·근거 충족, **partial**: 답변은 있으나 근거 일부 부족, **needs_review**: 사람 검토 필요, **missing**: 답변 없음.
- **Evidence status:** **SUFFICIENT**: 근거 충분, **PARTIAL**: 일부 부족, **MISMATCH**: 주제 불일치, **NONE**: 근거 없음, **ERROR**: 근거 처리 오류.
- **Rewrite / Polish:** **Rewrite**는 미달 답변 재작성, **Polish**는 수치·핵심 내용 변경 없이 문체를 자연스럽고 일관되게 다듬는 작업입니다.
- **Checkpoint / Resume:** **Checkpoint**는 단계별 임시 저장본, **Resume**은 처음부터 다시 하지 않고 저장본에서 이어서 실행하는 기능입니다.
- **Retry / Timeout:** **Retry**는 일시 오류 시 재시도, **Timeout**은 정해진 시간이 지나면 전체 정지를 막기 위해 해당 단계를 중단하는 제한입니다.
- **API / JSON:** **API**는 시스템 간 자동 데이터 교환 창구이고 **JSON**은 데이터를 전송·저장하는 구조화된 텍스트 형식입니다.
- **RAG:** 문서 저장소에서 관련 문단·표를 찾아 AI에 전달하는 방식입니다. RAG가 좋아야 AI가 올바른 근거로 작성할 수 있습니다.
- **Audit:** 답변이 어떤 출처와 행을 사용했고 어떤 검사를 거쳤는지 다시 확인할 수 있는 추적 기능입니다.
- **LangSmith:** AI 호출의 입력·출력, 시간, 오류를 추적해 문제 원인을 찾는 도구입니다.
- **Temporal:** 장시간 작업의 대기열, 재시도, 중단 후 재개를 관리하는 도구이며 프로젝트에서는 선택 기능입니다.
- **Manifest:** 각 Agent와 사용할 AI 모델, 지시문, Skill을 정리한 선언 파일입니다.

_최종 평가_

### 결론

> **아키텍처 방향은 적절하지만 자동 게시 품질은 아직 미달입니다.**
>
> 현재 시스템은 명확한 처리 흐름, 34개 역할, 31개 세부 기능, 문항별 데이터 분리, 이중 검사, 임시 저장, 출처 대조 기능을 갖추고 있습니다. 2026년 8월 10일 실행은 정성 표 처리와 정량 값 증가를 보여 주었습니다. 그러나 미달 35개, 빈 답변 13개, 표 문항 23개 중 미달 21개로 발행 전 사람의 검토가 필요합니다.

#### 전후 비교 결론

#### 명확한 개선

값이 있는 정량 항목 75→113, 표 문항 23개 처리 추가, Excel 대조 sheet 추가, 내용 누락과 반복 시작 문구 감소.

#### 부분 개선

통과 문항 3→5, 출처 부족 경고 감소는 있으나 문제 해결보다 탐지 개선의 비중이 큽니다.

#### 미개선

미달 28→35, 내용 있는 답변 83→82, 실행 시간 13.1% 증가, 표 문항 완전 통과 0개.

#### 영향도가 가장 큰 세 가지 우선순위

| #   | 우선순위                                                                           | 기대 효과                                                                         |
| --- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 1   | 숫자·단위 표현을 통일하고 원본 표의 정확한 행·셀 기준으로 검사합니다.              | 수치 대조 오류 69건을 줄이고 표 문항을 미달에서 검토 필요 또는 통과로 개선합니다. |
| 2   | 표를 찾지 못한 8개 문항과 누락된 필수 내용의 근거 검색을 개선합니다.               | 검사 기준을 낮추지 않고 출처 부족 경고를 줄입니다.                                |
| 3   | 근거 필터의 오류를 줄이고 수정할 데이터가 충분한 문항만 AI가 다시 작성하게 합니다. | 빈 답변, 근거 필터 오류, 실행 시간을 줄입니다.                                    |

> **최종 판단.**
>
> 2026년 8월 10일 버전은 데이터 구성, 값이 있는 정량 항목 수, 출처 추적 측면에서 개선되었지만 정성 답변 품질이 전반적으로 좋아진 것은 아닙니다. 현재는 “AI 초안 작성, 시스템 검사, 사람 최종 검토” 방식이 적절하며 완전 자동 발행 단계는 아닙니다.

출처: 참조 HTML 보고서 2개, 현재 역할 목록과 처리 구조, 2026년 8월 7일·2026년 8월 10일 대웅제약 결과 파일.
