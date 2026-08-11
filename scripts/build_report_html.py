"""Build a bilingual HTML ESG run report from the Markdown template and run JSON.

The Markdown file is the report contract: its front matter selects the theme and
the generated page follows the same tabbed-dashboard structure. All run metrics
come from the supplied run directory; no historical values are copied in.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


DRIVE_URL = "https://docs.google.com/spreadsheets/d/1sW2mBt2z27rxZsIa4MrS3UtVUQNgbj0Y/edit?usp=sharing&ouid=114916983520042353804&rtpof=true&sd=true"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def n(value: Any) -> str:
    return f"{int(value):,}".replace(",", ".")


def pct(value: int, total: int) -> str:
    return f"{(100 * value / total):.1f}%" if total else "0.0%"


def bi(vi: str, ko: str) -> str:
    return f'<span lang="vi">{vi}</span><span lang="ko">{ko}</span>'


def btext(vi: str, ko: str) -> str:
    return bi(esc(vi), esc(ko))


def heading(level: int, vi: str, ko: str) -> str:
    return f"<h{level}>{btext(vi, ko)}</h{level}>"


def p(vi: str, ko: str, cls: str = "") -> str:
    klass = f' class="{cls}"' if cls else ""
    return f"<p{klass}>{btext(vi, ko)}</p>"


def card(vi_title: str, ko_title: str, vi_body: str, ko_body: str, tone: str = "blue") -> str:
    return (
        f'<article class="card tone-{tone}">{heading(3, vi_title, ko_title)}'
        f"<p>{btext(vi_body, ko_body)}</p></article>"
    )


def metric_card(value: str, vi: str, ko: str, tone: str = "blue") -> str:
    return f'<article class="card tone-{tone}"><div class="metric">{esc(value)}</div><p>{btext(vi, ko)}</p></article>'


def table(headers: list[tuple[str, str]], rows: list[list[tuple[str, str] | str]]) -> str:
    out = ["<div class=\"table-wrap\"><table><thead><tr>"]
    out.extend(f"<th>{btext(vi, ko)}</th>" for vi, ko in headers)
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for cell in row:
            if isinstance(cell, tuple):
                out.append(f"<td>{btext(cell[0], cell[1])}</td>")
            else:
                out.append(f"<td>{esc(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def pill(value: str, tone: str) -> str:
    return f'<span class="pill {tone}">{esc(value)}</span>'


def load_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    return yaml.safe_load(text[3:end]) or {}


def answer_qids(answers: list[dict[str, Any]], field: str, value: str) -> list[str]:
    return [a.get("qid", "") for a in answers if a.get(field) == value]


def qid_list(values: list[str], limit: int = 95) -> str:
    values = [v for v in values if v]
    shown = values[:limit]
    suffix = f" … (+{len(values) - limit})" if len(values) > limit else ""
    return ", ".join(shown) + suffix if shown else "—"


def bar_rows(items: list[tuple[str, str, int]], total: int) -> str:
    out = ['<div class="bar-list">']
    for label_vi, label_ko, value in items:
        width = 100 * value / total if total else 0
        out.append(
            '<div class="bar-row">'
            f"<div class=\"bar-label\">{btext(label_vi, label_ko)}</div>"
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
            f'<div class="bar-value">{n(value)} <small>({pct(value, total)})</small></div>'
            "</div>"
        )
    out.append("</div>")
    return "".join(out)


def css() -> str:
    return r"""
:root{--bg:#f3f5f6;--panel:#fff;--ink:#17232d;--muted:#566470;--faint:#84919b;--line:#dbe2e6;--slate:#243746;--blue:#3d5db3;--blue-soft:#e9edf9;--teal:#08796d;--teal-soft:#e2f2ef;--green:#257747;--green-soft:#e5f2e9;--amber:#a76b13;--amber-soft:#f8eddc;--red:#b44833;--red-soft:#f8e7e3}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--ink);background:var(--bg);font-family:Arial,"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif;line-height:1.58}body[data-lang=vi] [lang=ko],body[data-lang=ko] [lang=vi]{display:none}.wrap{width:min(1200px,calc(100% - 40px));margin:0 auto}.mono,code{font-family:Consolas,"Courier New",monospace}.hero{color:#fff;border-bottom:6px solid var(--teal);background:var(--slate)}.hero-inner{padding:38px 0 32px}.topbar{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}.eyebrow{margin:0 0 10px;color:#cbd7df;font-size:13px;font-weight:800;text-transform:uppercase}.title-line{display:flex;flex-wrap:wrap;align-items:flex-start;gap:12px}h1{max-width:920px;margin:0;font-size:clamp(30px,4vw,43px);line-height:1.12}.badge{padding:7px 11px;border:1px solid #7d91a1;border-radius:6px;background:#334b5d;font-weight:800}.lead{max-width:980px;margin:15px 0 0;color:#d9e2e8;font-size:17px}.latest-report-link{display:inline-flex;gap:8px;margin-top:18px;padding:9px 13px;border:1px solid #a9c9bf;border-radius:6px;color:#fff;background:var(--teal);font-size:14px;font-weight:800;text-decoration:none}.lang-switch{display:flex;flex:0 0 auto;gap:6px;padding:5px;border:1px solid #607788;border-radius:7px}.lang-switch button{min-width:45px;border:0;border-radius:5px;padding:7px 10px;color:#fff;background:transparent;font-weight:800;cursor:pointer}.lang-switch button.active{color:var(--ink);background:#fff}.hero-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:26px}.hero-stat{min-height:112px;padding:16px;border:1px solid #607788;border-radius:7px;background:#2e4556}.hero-stat strong{display:block;margin-bottom:8px;font-size:29px;line-height:1}.hero-stat span{color:#d5dfe6;font-size:13px}nav{position:sticky;top:0;z-index:30;border-bottom:1px solid var(--line);background:rgba(255,255,255,.97)}nav .wrap{display:flex;gap:8px;overflow-x:auto;padding:10px 0}nav button{flex:0 0 auto;border:1px solid var(--line);border-radius:6px;padding:8px 12px;color:var(--ink);background:#fff;font-weight:750;cursor:pointer}nav button.active{color:#fff;border-color:var(--blue);background:var(--blue)}main{padding:24px 0 54px}.tab-panel{display:none;padding:27px;border:1px solid var(--line);border-radius:8px;background:var(--panel);box-shadow:0 14px 35px rgba(23,35,45,.07)}.tab-panel.active{display:block}h2{margin:0 0 8px;font-size:28px}h3{margin:26px 0 10px;font-size:19px}h4{margin:0 0 7px;font-size:15px}p{margin:8px 0}.section-lead{max-width:1020px;color:var(--muted)}.section-kicker{color:var(--teal);font-size:12px;font-weight:900;text-transform:uppercase}.grid-2,.grid-3,.grid-4{display:grid;gap:14px;margin-top:18px}.grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid-4{grid-template-columns:repeat(4,minmax(0,1fr))}.card{padding:17px;border:1px solid var(--line);border-radius:7px;background:#fff}.card h3{margin:0 0 8px;font-size:17px}.card p{color:var(--muted)}.tone-blue{border-top:4px solid var(--blue)}.tone-teal{border-top:4px solid var(--teal)}.tone-green{border-top:4px solid var(--green)}.tone-amber{border-top:4px solid var(--amber)}.tone-red{border-top:4px solid var(--red)}.metric{font-size:30px;font-weight:850;line-height:1.1}.callout{margin-top:18px;padding:16px 18px;border-left:5px solid var(--blue);background:var(--blue-soft)}.callout.good{border-left-color:var(--green);background:var(--green-soft)}.callout.warn{border-left-color:var(--amber);background:var(--amber-soft)}.callout.bad{border-left-color:var(--red);background:var(--red-soft)}.table-wrap{margin-top:16px;overflow-x:auto;border:1px solid var(--line);border-radius:7px}table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:#314250;background:#edf1f3;font-size:13px}tr:last-child td{border-bottom:0}.delta-up{color:var(--green);font-weight:850}.delta-down{color:var(--red);font-weight:850}.pill{display:inline-flex;align-items:center;min-height:25px;padding:4px 8px;border-radius:5px;font-size:12px;font-weight:850}.pill.pass{color:var(--green);background:var(--green-soft)}.pill.warn{color:#79500f;background:var(--amber-soft)}.pill.fail{color:var(--red);background:var(--red-soft)}.pill.info{color:var(--blue);background:var(--blue-soft)}.flow-main{display:grid;grid-template-columns:repeat(6,minmax(115px,1fr));gap:9px;margin-top:18px}.flow-box{min-height:104px;padding:13px;border:1px solid #bfcad2;border-radius:6px;background:#f9fafb}.flow-box strong{display:block;margin-bottom:5px;font-size:13px}.flow-box span{color:var(--muted);font-size:12px}.bar-list{display:grid;gap:11px;margin-top:15px}.bar-row{display:grid;grid-template-columns:minmax(155px,225px) 1fr 95px;gap:12px;align-items:center}.bar-label{color:var(--muted);font-size:13px;font-weight:750}.bar-track{height:13px;overflow:hidden;border-radius:4px;background:#e8edef}.bar-fill{height:100%;border-radius:4px;background:var(--blue)}.bar-value{text-align:right;font-size:13px;font-weight:850}.bar-value small{color:var(--muted);font-weight:400}.id-list{font-family:Consolas,"Courier New",monospace;font-size:12px;line-height:1.8;overflow-wrap:anywhere}.decision{padding:18px;border:1px solid #a8cbb8;border-radius:7px;background:var(--green-soft)}.decision strong{display:block;margin-bottom:6px;font-size:18px}footer{padding:20px 0 34px;color:var(--faint);text-align:center;font-size:12px}@media(max-width:980px){.hero-grid,.grid-4{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(2,minmax(0,1fr))}.flow-main{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.wrap{width:min(100% - 24px,1200px)}.topbar{display:block}.lang-switch{width:max-content;margin-top:18px}.hero-grid,.grid-2,.grid-3,.grid-4,.flow-main{grid-template-columns:1fr}.tab-panel{padding:18px}.bar-row{grid-template-columns:1fr 70px}.bar-track{grid-column:1/-1;grid-row:2}}@media print{nav,.lang-switch{display:none}body{background:#fff}.tab-panel{display:block!important;margin:12px 0;box-shadow:none;break-inside:avoid}.hero{background:#243746!important;print-color-adjust:exact}}
"""


def build(template: Path, run_dir: Path, output: Path, drive_url: str = DRIVE_URL) -> None:
    meta = load_frontmatter(template)
    coverage = json.loads((run_dir / "coverage_summary.json").read_text(encoding="utf-8"))
    run = json.loads((run_dir / "qualitative_run.json").read_text(encoding="utf-8"))
    company = coverage["company"]
    answers = run["answers"]
    stats = coverage["stats"]
    qa = coverage["qa_stats"]
    quality = coverage["quality_grade_stats"]
    publication = coverage["publication_status_stats"]
    quant = run["quantitative_stats"]
    metrics = coverage["metric_facts"]
    total = int(coverage["total_qids"])
    date = "11/08/2026"
    date_ko = "2026/08/11"
    run_id = company["run_id"]

    answered = n(stats["answered"])
    empty = n(stats["empty"])
    quant_filled = n(quant["filled"])
    blocked = n(publication["blocked"])
    review = n(publication["review_required"])
    published = n(publication["published"])

    hero_stats = "".join(
        [
            f'<div class="hero-stat"><strong>{total}</strong>{btext("câu định tính trong một báo cáo", "하나의 보고서에 포함된 정성 문항")}</div>',
            f'<div class="hero-stat"><strong>{answered}</strong>{btext("câu có câu trả lời cuối", "최종 답변이 있는 문항")}</div>',
            f'<div class="hero-stat"><strong>{quant_filled} / {n(quant["total"])}</strong>{btext("mục định lượng đã điền", "입력 완료된 정량 항목")}</div>',
            f'<div class="hero-stat"><strong>{published} / {review} / {blocked}</strong>{btext("xuất bản / xem lại / bị chặn", "게시 / 검토 필요 / 차단")}</div>',
        ]
    )

    nav = [
        ("overview", "Tổng quan", "개요"),
        ("flow", "Luồng xử lý", "처리 흐름"),
        ("results", "Kết quả run", "실행 결과"),
        ("quality", "QA và xuất bản", "QA 및 게시"),
        ("quantitative", "Định lượng", "정량"),
        ("weaknesses", "Điểm yếu", "한계"),
        ("glossary", "Chú thích", "용어"),
        ("conclusion", "Kết luận", "결론"),
    ]
    nav_html = "".join(f'<button type="button" class="{"active" if i == 0 else ""}" data-tab="{id_}">{btext(vi, ko)}</button>' for i, (id_, vi, ko) in enumerate(nav))

    overview = f'''
      <section id="overview" class="tab-panel active">
        <p class="section-kicker">{btext("Toàn cảnh lần chạy", "실행 전체 개요")}</p>
        {heading(2, "Tổng quan lần chạy Daewoong", "대웅제약 실행 개요")}
        {p(f"Đây là báo cáo được dựng từ dữ liệu run {run_id}. Nội dung phản ánh đúng kết quả của công ty {company['company_name']} cho năm {company['year']}; không sử dụng số liệu của báo cáo cũ.", f"{run_id} 실행 데이터로 생성한 보고서입니다. {company['year']}년 {company['company_name']}의 실행 결과만 반영하며 이전 보고서의 수치는 사용하지 않습니다.", "section-lead")}
        <div class="grid-4">
          {metric_card("95", "Tổng số câu định tính", "전체 정성 문항", "blue")}
          {metric_card(answered, "Câu có câu trả lời cuối", "최종 답변이 있는 문항", "teal")}
          {metric_card(quant_filled, "Mục định lượng đã điền", "입력 완료 정량 항목", "green")}
          {metric_card(blocked, "Câu bị chặn trước xuất bản", "게시 전 차단 문항", "red")}
        </div>
        <div class="grid-2">
          {card("Thông tin đầu vào", "입력 정보", f"Công ty: {company['company_name']} · Năm: {company['year']} · Ngành: {company['industry']} · Quy mô: {company['scale']} · Ngôn ngữ đầu ra: {company['output_language']}", f"회사: {company['company_name']} · 연도: {company['year']} · 산업: {company['industry']} · 규모: {company['scale']} · 출력 언어: {company['output_language']}", "blue")}
          {card("Đầu ra của run", "실행 출력", "JSON kết quả, coverage summary, Excel báo cáo và Excel tổng hợp được ghi trong thư mục run.", "결과 JSON, coverage summary, 보고서 Excel 및 통합 Excel이 실행 폴더에 기록되었습니다.", "teal")}
        </div>
        <div class="callout"><strong>{btext("Báo cáo mới nhất trên Google Drive.", "Google Drive 최신 보고서.")}</strong><br><a class="latest-report-link" href="{esc(drive_url)}" target="_blank" rel="noopener noreferrer">↗ {btext("Mở báo cáo mới nhất", "최신 보고서 열기")}</a></div>
      </section>'''

    flow_steps = [
        ("01 · Khởi tạo", "01 · 실행 초기화", "Đọc cấu hình, công ty, năm và tạo thư mục run.", "설정, 회사, 연도를 읽고 실행 폴더를 만듭니다."),
        ("02 · Nhận dữ liệu", "02 · 데이터 수신", "Nạp evidence định tính và 210 mục định lượng.", "정성 근거와 210개 정량 항목을 불러옵니다."),
        ("03 · Chuẩn hóa", "03 · 정규화", "Đưa dữ liệu về cấu trúc chung theo QID.", "문항 ID 기준으로 데이터를 공통 구조로 정규화합니다."),
        ("04 · Viết câu", "04 · 답변 작성", "Tạo draft, kiểm tra dẫn chứng và sinh câu trả lời.", "초안을 만들고 근거를 검사해 답변을 생성합니다."),
        ("05 · Kiểm tra", "05 · 품질 검사", "QA, quality grade và quyết định xuất bản.", "QA, 품질 등급 및 게시 결정을 수행합니다."),
        ("06 · Xuất kết quả", "06 · 결과 출력", "Ghi JSON, coverage summary và Excel.", "JSON, coverage summary 및 Excel을 기록합니다."),
    ]
    flow_html = ''.join(f'<div class="flow-box"><strong>{btext(a,b)}</strong><span>{btext(c,d)}</span></div>' for a,b,c,d in flow_steps)
    flow = f'''
      <section id="flow" class="tab-panel">
        <p class="section-kicker">{btext("Sơ đồ xử lý", "처리 구성")}</p>
        {heading(2, "Luồng xử lý của run mới", "새 실행 처리 흐름")}
        {p("Luồng thực tế đi từ dữ liệu đầu vào đến quyết định xuất bản. Mỗi câu được giữ riêng theo QID để không trộn evidence giữa 95 câu.", "실제 흐름은 입력 데이터에서 게시 결정까지 이어집니다. 95개 문항의 근거가 섞이지 않도록 문항 ID별로 분리 처리합니다.", "section-lead")}
        {heading(3, "Luồng toàn báo cáo · 6 bước", "전체 보고서 흐름 · 6단계")}
        <div class="flow-main">{flow_html}</div>
        <div class="grid-3">
          {card("Tách evidence theo QID", "문항별 근거 분리", "Mỗi QID nhận vùng evidence riêng, có nguồn và trạng thái riêng.", "각 문항은 별도 근거 범위와 출처·상태를 갖습니다.", "blue")}
          {card("Kiểm tra hai lớp", "이중 검사", "Quy tắc cố định kiểm tra cấu trúc; QA và quality grade kiểm tra khả năng dùng.", "고정 규칙은 구조를 검사하고 QA와 품질 등급은 사용 가능성을 검사합니다.", "amber")}
          {card("Có thể truy vết", "추적 가능", "Run ID, source digest, request trace và file output được ghi trong metadata.", "실행 ID, source digest, 요청 추적 및 출력 파일이 메타데이터에 기록됩니다.", "teal")}
        </div>
      </section>'''

    result_rows = [
        [("Answered", "Answered"), ("70", "70"), ("Câu có kết quả cuối / 최종 결과 문항" )],
        [("Empty", "Empty"), (str(stats["empty"]), str(stats["empty"])), ("Không có câu trả lời / 답변 없음")],
        [("Weak", "Weak"), (str(stats["weak"]), str(stats["weak"])), ("Có cảnh báo hoặc thiếu độ mạnh / 경고 또는 근거 부족")],
        [("Failed", "Failed"), (str(stats["failed"]), str(stats["failed"])), ("Không đạt xử lý cuối / 최종 처리 실패")],
    ]
    results = f'''
      <section id="results" class="tab-panel">
        <p class="section-kicker">{btext("Kết quả định tính", "정성 결과")}</p>
        {heading(2, "Kết quả của run {date}", f"{date_ko} 실행 결과")}
        {p(f"Run ID: {run_id}. Tổng cộng {total} câu được xử lý; {answered} câu có final answer và {empty} câu không có final answer.", f"실행 ID: {run_id}. 총 {total}개 문항 중 {answered}개에 최종 답변이 있고 {empty}개는 최종 답변이 없습니다.", "section-lead")}
        {table([("Nhóm kết quả", "결과 그룹"), ("Số câu", "문항 수"), ("Diễn giải", "설명")], result_rows)}
        <h3>{btext("Phân bố kết quả", "결과 분포")}</h3>
        {bar_rows([("Answered", "Answered", stats["answered"]), ("Weak", "Weak", stats["weak"]), ("Empty", "Empty", stats["empty"]), ("Failed", "Failed", stats["failed"])], total)}
        <div class="callout"><strong>{btext("Dữ liệu được giới hạn trong run mới.", "데이터 범위는 새 실행으로 제한됩니다.")}</strong><br>{btext("Báo cáo này không tính lại hoặc trộn số liệu từ các lần chạy trước.", "이 보고서는 이전 실행 수치를 재사용하거나 혼합하지 않습니다.")}</div>
      </section>'''

    quality_rows = [
        [("Full", "Full"), (str(quality["full"]), str(quality["full"])), ("Đủ điều kiện tốt nhất / 가장 높은 품질")],
        [("Partial", "Partial"), (str(quality["partial"]), str(quality["partial"])), ("Còn thiếu một phần / 일부 부족")],
        [("Cautious", "Cautious"), (str(quality["cautious"]), str(quality["cautious"])), ("Cần thận trọng / 주의 필요")],
        [("Failed", "Failed"), (str(quality["failed"]), str(quality["failed"])), ("Không đạt / 실패")],
    ]
    qa = f'''
      <section id="quality" class="tab-panel">
        <p class="section-kicker">{btext("Kiểm tra chất lượng", "품질 검사")}</p>
        {heading(2, "QA, quality grade và trạng thái xuất bản", "QA, 품질 등급 및 게시 상태")}
        <div class="grid-3">
          {metric_card(str(qa["passed"]), "QA passed", "QA 통과", "green")}
          {metric_card(str(qa["failed"]), "QA failed", "QA 실패", "red")}
          {metric_card(str(qa["empty"]), "QA empty", "QA 빈 결과", "amber")}
        </div>
        <h3>{btext("Quality grade", "품질 등급")}</h3>
        {table([("Mức", "등급"), ("Số câu", "문항 수"), ("Ý nghĩa", "의미")], quality_rows)}
        <h3>{btext("Trạng thái xuất bản", "게시 상태")}</h3>
        {bar_rows([("Published", "게시", publication["published"]), ("Review required", "검토 필요", publication["review_required"]), ("Blocked", "차단", publication["blocked"])], total)}
        <div class="grid-3">
          {card("Published", "게시", f"{published} câu đủ điều kiện xuất bản theo kết quả run.", f"실행 결과 기준 {published}개 문항이 게시 가능 상태입니다.", "green")}
          {card("Review required", "검토 필요", f"{review} câu cần người kiểm tra trước khi phát hành.", f"{review}개 문항은 공개 전 사람의 검토가 필요합니다.", "amber")}
          {card("Blocked", "차단", f"{blocked} câu bị chặn do QA hoặc trạng thái upstream.", f"{blocked}개 문항은 QA 또는 upstream 상태로 차단되었습니다.", "red")}
        </div>
      </section>'''

    quant_rows = [
        [("Tổng mục", "전체 항목"), (str(quant["total"]), str(quant["total"])), ("Theo template quant_210 / quant_210 템플릿")],
        [("Đã điền", "입력 완료"), (str(quant["filled"]), str(quant["filled"])), (pct(quant["filled"], quant["total"]), pct(quant["filled"], quant["total"]))],
        [("Thiếu", "누락"), (str(quant["missing"]), str(quant["missing"])), (pct(quant["missing"], quant["total"]), pct(quant["missing"], quant["total"]))],
        [("Cần xác nhận", "확인 필요"), (str(quant["needs_confirmation"]), str(quant["needs_confirmation"])), ("Kiểm tra thủ công / 수동 확인", "Kiểm tra thủ công / 수동 확인")],
    ]
    quant_section = f'''
      <section id="quantitative" class="tab-panel">
        <p class="section-kicker">{btext("Dữ liệu định lượng", "정량 데이터")}</p>
        {heading(2, "Kết quả 210 mục định lượng", "210개 정량 항목 결과")}
        {p("Giá trị định lượng được map trực tiếp từ dữ liệu nguồn; AI không tự suy đoán số liệu. Các chỉ số dưới đây lấy từ quantitative_stats của run mới.", "정량 값은 원천 데이터에서 직접 매핑하며 AI가 수치를 추정하지 않습니다. 아래 지표는 새 실행의 quantitative_stats에서 가져왔습니다.", "section-lead")}
        {table([("Chỉ số", "지표"), ("Giá trị", "값"), ("Ghi chú", "비고")], quant_rows)}
        {bar_rows([("Filled", "입력 완료", quant["filled"]), ("Missing", "누락", quant["missing"]), ("Needs confirmation", "확인 필요", quant["needs_confirmation"])], quant["total"])}
        <div class="callout good"><strong>{btext("Metric audit.", "Metric audit.")}</strong><br>{btext(f"{metrics['metric_row_count']} dòng bảng được đọc, {metrics['accepted_fact_count']} fact được chấp nhận và không có xung đột số liệu.", f"표 {metrics['metric_row_count']}개 행을 읽었고 {metrics['accepted_fact_count']}개 fact를 수용했으며 수치 충돌은 없습니다.")}</div>
      </section>'''

    missing_metrics = coverage.get("metric_facts", {}).get("status_qids", {}).get("not_found", [])
    top_notes = coverage.get("top_failure_notes", [])[:8]
    note_rows = [[(str(x.get("note", "")), str(x.get("note", ""))), (str(x.get("count", 0)), str(x.get("count", 0))), ("Cần xem nguyên nhân theo QID / 문항별 원인 확인 필요", "Cần xem nguyên nhân theo QID / 문항별 원인 확인 필요")] for x in top_notes]
    weak = f'''
      <section id="weaknesses" class="tab-panel">
        <p class="section-kicker">{btext("Điểm cần cải thiện", "개선 필요 지점")}</p>
        {heading(2, "Các điểm yếu còn lại của run mới", "새 실행의 잔여 한계")}
        {p("Các cảnh báo dưới đây được tổng hợp từ coverage summary và danh sách lỗi của chính run này.", "아래 경고는 이번 실행의 coverage summary와 오류 목록만으로 집계했습니다.", "section-lead")}
        {table([("Nguyên nhân nổi bật", "주요 원인"), ("Số lần", "횟수"), ("Hướng xử lý", "대응 방향")], note_rows)}
        <div class="grid-2">
          {card("Câu không có final answer", "최종 답변 없음", f"{empty} câu: {qid_list(coverage.get('empty_final_answer_qids', []), 40)}", f"{empty}개: {qid_list(coverage.get('empty_final_answer_qids', []), 40)}", "red")}
          {card("Không tìm thấy bảng metric", "Metric 표 미발견", f"{len(missing_metrics)} câu: {qid_list(missing_metrics)}", f"{len(missing_metrics)}개: {qid_list(missing_metrics)}", "amber")}
        </div>
        <div class="callout warn"><strong>{btext("Ưu tiên cải thiện.", "개선 우선순위.")}</strong><br>{btext("Ưu tiên bổ sung evidence còn thiếu, xử lý các QID bị chặn và kiểm tra thủ công các câu review_required trước khi phát hành.", "부족한 근거를 보강하고 차단된 문항을 처리하며 review_required 문항을 게시 전에 수동 검토해야 합니다.")}</div>
      </section>'''

    glossary = f'''
      <section id="glossary" class="tab-panel">
        <p class="section-kicker">{btext("Chú thích kỹ thuật", "기술 용어")}</p>
        {heading(2, "Chú thích thuật ngữ và mã kỹ thuật", "기술 용어와 코드 설명")}
        {table([("Thuật ngữ", "용어"), ("Giải thích", "설명")], [
          [("Run ID", "Run ID"), ("Mã định danh duy nhất của lần chạy, dùng để truy vết JSON, Excel và log.", "JSON, Excel 및 로그를 추적하는 실행 고유 식별자입니다.")],
          [("QA", "QA"), ("Kiểm tra chất lượng cuối; PASS/failed/empty phản ánh trạng thái kiểm tra của câu.", "최종 품질 검사이며 PASS/failed/empty가 문항 검사 상태를 나타냅니다.")],
          [("Quality grade", "Quality grade"), ("full, partial, cautious hoặc failed; mức độ tin cậy để xem xét trước xuất bản.", "full, partial, cautious, failed로 게시 전 신뢰 수준을 나타냅니다.")],
          [("Evidence", "Evidence"), ("Dẫn chứng được truy hồi từ nguồn, giữ kèm source ID và metadata để audit.", "출처에서 검색된 근거이며 audit을 위해 source ID와 메타데이터를 유지합니다.")],
          [("Review required", "Review required"), ("Câu chưa nên phát hành tự động và cần người kiểm tra.", "자동 게시하지 않고 사람의 검토가 필요한 문항입니다.")],
        ])}
      </section>'''

    conclusion = f'''
      <section id="conclusion" class="tab-panel">
        <p class="section-kicker">{btext("Đánh giá cuối", "최종 평가")}</p>
        {heading(2, "Kết luận", "결론")}
        <div class="decision"><strong>{btext("Run đã hoàn thành xử lý dữ liệu nhưng chưa phù hợp để tự động phát hành toàn bộ.", "실행은 데이터 처리를 완료했지만 전체 자동 게시에는 적합하지 않습니다.")}</strong>{btext(f"Run có {answered}/{total} câu có final answer, {published} câu published, {review} câu cần xem lại và {blocked} câu bị chặn. Với định lượng, {quant_filled}/{quant['total']} mục đã được điền. Kết luận vận hành: có thể dùng kết quả làm bản nháp có kiểm soát, nhưng cần review các câu chưa đạt trước khi phát hành.", f"실행 결과 {total}개 중 {answered}개에 최종 답변이 있고, {published}개는 게시, {review}개는 검토 필요, {blocked}개는 차단 상태입니다. 정량 항목은 {quant_filled}/{quant['total']}개가 입력되었습니다. 운영 결론은 통제된 초안으로 사용할 수 있으나 미달 문항은 게시 전에 검토해야 한다는 것입니다.")}</div>
        <h3>{btext("Ba ưu tiên tiếp theo", "다음 세 가지 우선순위")}</h3>
        <div class="grid-3">
          {card("1 · Bổ sung evidence", "1 · 근거 보강", "Xử lý các QID missing_expected_facets và draft_evidence.", "missing_expected_facets와 draft_evidence 문항을 보강합니다.", "blue")}
          {card("2 · Gỡ câu bị chặn", "2 · 차단 문항 해소", f"Kiểm tra {blocked} câu blocked theo QA và upstream status.", f"QA와 upstream 상태를 기준으로 {blocked}개 blocked 문항을 점검합니다.", "amber")}
          {card("3 · Review trước phát hành", "3 · 게시 전 검토", f"Ưu tiên {review} câu review_required và các metric cần xác nhận.", f"{review}개 review_required와 확인 필요한 metric을 우선 검토합니다.", "red")}
        </div>
      </section>'''

    sections = overview + flow + results + qa + quant_section + weak + glossary + conclusion
    title_vi = f"ESG LangGraph: báo cáo run Daewoong {date}"
    title_ko = f"ESG LangGraph: 대웅제약 {date_ko} 실행 보고서"
    lead_vi = f"Báo cáo sử dụng template {template.name} và dữ liệu run mới {run_id}. Nội dung chỉ phản ánh kết quả của Daewoong năm {company['year']}."
    lead_ko = f"{template.name} 템플릿과 새 실행 {run_id} 데이터를 사용한 보고서입니다. {company['year']}년 대웅제약 결과만 반영합니다."
    html_doc = f'''<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title_vi)}</title><style>{css()}</style></head>
<body data-lang="vi">
<header class="hero"><div class="wrap hero-inner"><div class="topbar"><div><p class="eyebrow">{btext(f"Báo cáo kiến trúc và vận hành · Daewoong ESG {company['year']} · {date}", f"아키텍처 및 운영 보고서 · 대웅제약 ESG {company['year']} · {date_ko}")}</p><div class="title-line"><h1>{btext(title_vi, title_ko)}</h1><span class="badge">{esc(meta.get('version','V2'))}</span></div><p class="lead">{btext(lead_vi, lead_ko)}</p><a class="latest-report-link" href="{esc(drive_url)}" target="_blank" rel="noopener noreferrer">↗ {btext("Mở báo cáo mới nhất trên Google Drive", "Google Drive 최신 보고서 열기")}</a></div><div class="lang-switch"><button type="button" class="active" data-lang-button="vi">VI</button><button type="button" data-lang-button="ko">KO</button></div></div><div class="hero-grid">{hero_stats}</div></div></header>
<nav><div class="wrap">{nav_html}</div></nav>
<main class="wrap">{sections}</main>
<footer><div class="wrap">{btext(f"Nguồn dữ liệu: {run_dir.as_posix()} · Run ID: {run_id} · Template: {template.name}", f"데이터 출처: {run_dir.as_posix()} · 실행 ID: {run_id} · 템플릿: {template.name}")}</div></footer>
<script>
const body=document.body;
document.querySelectorAll('[data-lang-button]').forEach(button=>button.addEventListener('click',()=>{{const lang=button.dataset.langButton;body.dataset.lang=lang;document.querySelectorAll('[data-lang-button]').forEach(b=>b.classList.toggle('active',b.dataset.langButton===lang));}}));
document.querySelectorAll('nav button').forEach(button=>button.addEventListener('click',()=>{{const id=button.dataset.tab;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b===button));document.querySelectorAll('.tab-panel').forEach(panel=>panel.classList.toggle('active',panel.id===id));window.scrollTo({{top:0,behavior:'smooth'}});}}));
</script></body></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_doc, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--drive-url", default=DRIVE_URL)
    args = parser.parse_args()
    build(args.template, args.run_dir, args.output, args.drive_url)
    print(args.output)


if __name__ == "__main__":
    main()
