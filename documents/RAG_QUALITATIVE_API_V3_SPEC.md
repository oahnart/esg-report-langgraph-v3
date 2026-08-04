# RAG Qualitative Evidence API v3 Specification

> Status: Proposed  
> Version: 1.0  
> Date: 2026-08-04  
> Intended implementer: Team RAG  
> Consumer: ESG Report LangGraph

## 1. Purpose

This document specifies the next qualitative evidence retrieval API used by the ESG Report LangGraph.

The new contract must allow the consumer to distinguish between:

1. evidence that is similar to the question;
2. evidence that directly answers the question;
3. evidence that covers only part of the required disclosure;
4. evidence that comes from a draft, proposal, external assessment, or approved operating document;
5. a successful retrieval request that still contains insufficient evidence for a customer-facing answer.

The most important requirement is that retrieval confidence must not be treated as answer completeness. A result may have highly relevant documents but still be unanswerable because a required value, reporting period, target, accountable body, or control activity is absent.

## 2. Scope

### 2.1 In scope

- Qualitative ESG evidence retrieval by `company_id`, `year`, and question IDs.
- Question-level answerability and facet coverage.
- Evidence ranking, provenance, document status, and exact source locators.
- Evidence deduplication.
- A clean evidence-only normalized summary.
- Explicit responses for questions with no evidence or insufficient evidence.
- Backward-compatible migration from `/qualitative/evidence/v2`.

### 2.2 Out of scope

- A separate quantitative metrics API.
- Calculation or aggregation of company metrics.
- Writing the final ESG report answer.
- Legal approval of disclosures.
- Inferring facts, commitments, targets, or performance that are absent from source documents.

The qualitative endpoint may still receive a question whose pillar is `metrics`. In that case it must return `answerable=true` only if the retrieved documents contain an actual metric result and a reporting period. Otherwise it must report a data gap and must not substitute a management process, target, or unrelated metric.

## 3. Normative language

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** indicate requirement priority.

## 4. Endpoint

```text
POST {TEAM_RAG_BASE_URL}/qualitative/evidence/v3
```

### 4.1 Headers

```http
Content-Type: application/json
Accept: application/json
X-Request-ID: optional-client-request-id
```

If `X-Request-ID` is provided, the service SHOULD return the same value as `request_id`. Otherwise, the service MUST generate a request ID.

## 5. Request contract

The four v2 fields remain valid and required. A v2-compatible request therefore remains valid for v3.

```json
{
  "company_id": "iljinhysolus",
  "item_ids": ["Q016", "Q003", "Q047"],
  "top_k": 5,
  "year": 2025
}
```

### 5.1 Request fields

| Field | Type | Required | Validation | Description |
|---|---|---:|---|---|
| `company_id` | string | yes | `^[a-z0-9][a-z0-9_-]{1,99}$` | Stable company identifier. |
| `item_ids` | array[string] | yes | 1–100 unique values | Qualitative template question IDs. |
| `top_k` | integer | yes | 1–20 | Maximum evidence items returned per question after deduplication. |
| `year` | integer | yes | 2000–2100 | Requested reporting year. |
| `options` | object | no | See below | Optional retrieval behavior. |

### 5.2 Optional request options

```json
{
  "options": {
    "output_language": "ko",
    "include_normalized_answer": true,
    "include_debug_metadata": false,
    "preferred_source_tiers": [
      "tier_1_governing",
      "tier_2_operational",
      "tier_3_assessment",
      "tier_4_draft"
    ],
    "exclude_document_statuses": []
  }
}
```

All options are optional. If omitted, the server MUST apply safe defaults and process the request successfully.

## 6. Response contract

```json
{
  "company_id": "iljinhysolus",
  "request_id": "rag_req_01K1ABCDEF",
  "api_version": "3.0",
  "rag_version": "2.3.0",
  "index_version": "iljinhysolus_20260801",
  "generated_at": "2026-08-04T09:30:00+07:00",
  "latency_ms": 842,
  "results": []
}
```

### 6.1 Top-level fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `company_id` | string | yes | Must match the requested company. |
| `request_id` | string | yes | Unique trace ID for this request. |
| `api_version` | string | yes | Contract version, initially `3.0`. |
| `rag_version` | string | yes | Deployed RAG application/model version. |
| `index_version` | string | yes | Search index or corpus snapshot used. |
| `generated_at` | RFC 3339 datetime | yes | Time the response was produced. |
| `latency_ms` | integer | yes | Total server processing time. |
| `results` | array | yes | Exactly one result for every requested `item_id`. |
| `warnings` | array[string] | no | Non-fatal request-level warnings. |

### 6.2 Completeness invariant

The response MUST contain exactly one result for every unique `item_id` in the request.

- The server MUST NOT omit unanswered question IDs.
- The server MUST NOT return unrequested question IDs.
- The server SHOULD preserve request order.
- A question with no evidence must still return a result with `coverage_status=no_evidence` and `items=[]`.

## 7. Question result schema

```json
{
  "question_id": "Q047",
  "question_ko": "오염물질 배출량 현황에 대해 회사의 현황과 정책을 설명해 주세요.",
  "pillar": "metrics",
  "normalized_answer_ko": "",
  "answer_status": "insufficient",
  "retrieval_confidence": 0.88,
  "coverage_status": "insufficient",
  "answerable": false,
  "covered_facets": ["management_process"],
  "missing_facets": ["metric_result", "reporting_period"],
  "failure_code": "MISSING_REQUIRED_FACETS",
  "failure_reason": "Evidence describes an air-emission management process but contains no actual pollutant emission result for the reporting period.",
  "retrieval_notes": [
    "Greenhouse-gas evidence was excluded because the question asks for pollutant emissions."
  ],
  "coverage": {
    "direct_answer": false,
    "supports_policy_or_direction": true,
    "supports_target": false,
    "supports_accountable_body": true,
    "supports_role": true,
    "supports_oversight_cadence": true,
    "supports_risk_identification": false,
    "supports_control_or_response": true,
    "supports_monitoring_follow_up": true,
    "supports_metric_result": false,
    "supports_reporting_period": false
  },
  "items": []
}
```

### 7.1 Required result fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `question_id` | string | yes | Requested question ID. |
| `question_ko` | string | yes | Canonical question text used by retrieval. |
| `pillar` | enum | yes | `strategy`, `governance`, `risk_management`, or `metrics`. |
| `normalized_answer_ko` | string | yes | Evidence-only normalized summary; empty when no safe direct summary is possible. |
| `answer_status` | enum | yes | Backward-compatible answer status. See Section 9. |
| `retrieval_confidence` | number | yes | Calibrated value from 0 to 1 measuring retrieval confidence only. |
| `coverage_status` | enum | yes | `complete`, `partial`, `insufficient`, or `no_evidence`. |
| `answerable` | boolean | yes | Whether the evidence can support a customer-facing answer to the requested question. |
| `covered_facets` | array[string] | yes | Supported facets. Empty array when none are supported. |
| `missing_facets` | array[string] | yes | Required or expected facets absent from evidence. |
| `failure_code` | string or null | yes | Machine-readable reason when not complete. |
| `failure_reason` | string | yes | Human-readable explanation; empty only for complete results. |
| `retrieval_notes` | array[string] | yes | Non-evidence retrieval observations. Must not be inserted into the normalized answer. |
| `coverage` | object | yes | Structured facet coverage booleans. |
| `items` | array | yes | Ranked, deduplicated evidence items. |

### 7.2 `answerable` semantics

`answerable=true` means the evidence supports at least a useful direct answer to the actual question.

It MUST NOT mean only that similar documents were found.

| `coverage_status` | `answerable` | Meaning |
|---|---:|---|
| `complete` | true | All required facets are supported. |
| `partial` | true | A useful direct answer is supported, but an expected or non-critical facet is missing. |
| `insufficient` | false | Documents exist, but one or more required facets are missing or the evidence is wrong-topic. |
| `no_evidence` | false | No eligible evidence was found. |

## 8. Question pillars and facets

The RAG service SHOULD maintain the question contract by `question_id`. The following rules define the minimum facet requirements.

### 8.1 Strategy

- Required: `policy_or_direction`
- Expected when the question asks for a goal, target, reduction, or achievement: `target`

### 8.2 Governance

- Required: `accountable_body`
- Required: `role`
- Expected: `oversight_cadence`

### 8.3 Risk management

- Required: `risk_identification`
- Required: `control_or_response`
- Expected: `monitoring_follow_up`

### 8.4 Metrics

- Required: `metric_result`
- Required: `reporting_period`

A target is not a metric result. A procedure is not a metric result. A reporting frequency is not a reporting period. A greenhouse-gas value is not a pollutant-emission value unless the question explicitly asks for greenhouse-gas emissions.

## 9. Status rules

### 9.1 Backward-compatible `answer_status`

Allowed values:

```text
high_confidence
medium_confidence
thin_but_usable
insufficient
no_evidence
```

Recommended mapping:

| Condition | `answer_status` | `coverage_status` |
|---|---|---|
| Complete, strong provenance | `high_confidence` | `complete` |
| Complete, moderate provenance | `medium_confidence` | `complete` |
| Useful partial answer | `thin_but_usable` | `partial` |
| Required facet missing or wrong-topic | `insufficient` | `insufficient` |
| No eligible evidence | `no_evidence` | `no_evidence` |

The service MUST NOT return `high_confidence` for a result missing a required facet.

### 9.2 Failure codes

Allowed initial values:

```text
NO_EVIDENCE
ALL_EVIDENCE_WEAK
MISSING_REQUIRED_FACETS
WRONG_TOPIC
SCOPE_LIMITED
DRAFT_ONLY
ASSESSMENT_ONLY
MISSING_SOURCE_PATH
CONFLICTING_EVIDENCE
UNSUPPORTED_REPORTING_PERIOD
INTERNAL_RETRIEVAL_ERROR
```

`failure_code` may be null only when `coverage_status=complete`.

## 10. Evidence item schema

```json
{
  "score": 0.91,
  "vector_score": 0.86,
  "reranker_score": 0.91,
  "semantic_score": 0.78,
  "semantic_label": "useful",
  "semantic_reason": "Approved air-management procedure directly supports operating controls.",
  "raw_evidence_ko": "...",
  "source_name": "ENV100 대기관리 프로세스.pdf",
  "source_path": "Ecovadis 업로드 자료/일진_Ecovadis_환경/ENV100 대기관리 프로세스.pdf",
  "document_id": "doc_env100",
  "chunk_id": "doc_env100_p4_c1",
  "canonical_source_id": "src_env100",
  "source_type": "policy_procedure",
  "document_status": "effective",
  "source_tier": "tier_1_governing",
  "document_version": "06",
  "effective_date": null,
  "topic": "pollution_and_emissions",
  "subtopic": "air_pollutant_management",
  "locator": {
    "page": 4,
    "sheet_name": null,
    "slide_number": null,
    "section": "4.2 대기배출 시설 운영",
    "paragraph": null,
    "cell_range": null
  }
}
```

### 10.1 Required evidence fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `score` | number | yes | Backward-compatible final ranking score, 0–1. |
| `vector_score` | number or null | yes | Vector retrieval score, calibrated to 0–1 if available. |
| `reranker_score` | number or null | yes | Reranker score, calibrated to 0–1 if available. |
| `semantic_score` | number | yes | Semantic relevance to the exact question, 0–1. |
| `semantic_label` | enum | yes | `useful`, `partial`, `weak`, `irrelevant`, or `no_match`. |
| `semantic_reason` | string | yes | Concise reason for the semantic label. |
| `raw_evidence_ko` | string | yes | Exact evidence excerpt. |
| `source_name` | string | yes | Human-readable source filename/title. |
| `source_path` | string | yes | Stable repository-relative source path. |
| `document_id` | string | yes | Stable document identifier. |
| `chunk_id` | string | yes | Stable chunk identifier. |
| `canonical_source_id` | string | yes | Canonical ID used for deduplication and citations. |
| `source_type` | enum | yes | Document type. |
| `document_status` | enum | yes | Approval/operational status. |
| `source_tier` | enum | yes | Evidence authority tier. |
| `document_version` | string or null | yes | Version or revision when known. |
| `effective_date` | date or null | yes | Effective/approval date when known. |
| `topic` | string | yes | Canonical ESG topic. |
| `subtopic` | string | yes | More specific evidence topic. |
| `locator` | object | yes | Exact location inside the source. |

## 11. Source classification

### 11.1 Source types

Initial allowed values:

```text
policy
policy_procedure
operating_procedure
manual
operational_record
performance_report
board_record
committee_record
external_assessment
certification
consultant_material
proposal
unknown
```

### 11.2 Document statuses

```text
approved
effective
operational
historical
external_assessment
draft
proposal
consultant_material
superseded
unknown
```

### 11.3 Source tiers

| Tier | Meaning | Examples |
|---|---|---|
| `tier_1_governing` | Approved or effective governing source | Policy, approved procedure, board resolution |
| `tier_2_operational` | Evidence of actual operation or performance | Logs, monitoring records, operating reports |
| `tier_3_assessment` | Third-party or customer assessment | EcoVadis/customer assessment |
| `tier_4_draft` | Proposed, draft, or consultant-created material | TF proposal, draft strategy |
| `tier_unknown` | Insufficient metadata | Unclassified source |

### 11.4 Provenance rules

- A draft or proposal MAY support only explicitly attributed proposed, planned, or under-review statements.
- A draft or proposal MUST NOT prove that a policy, governance body, target, commitment, or process is approved or operational.
- An external assessment MAY prove the assessment result and assessed content.
- An external assessment MUST NOT by itself prove that an internal policy is approved or implemented.
- A governing procedure MAY prove policy/process design but does not automatically prove actual performance.
- An operational record or performance report is preferred for actual activities and results.

## 12. Ranking and deduplication

### 12.1 Ranking

Final evidence order SHOULD consider:

1. exact question/subtopic alignment;
2. required facet coverage;
3. source tier;
4. document status;
5. reporting-year relevance;
6. reranker score;
7. vector score.

High vector similarity MUST NOT override a topic mismatch or missing required facet.

### 12.2 Deduplication

The service MUST deduplicate before applying `top_k`.

Primary deduplication key:

```text
canonical_source_id + chunk_id
```

Fallback key when a stable chunk ID is unavailable:

```text
canonicalized_source_path + normalized_evidence_hash
```

Filename-only and full-path references to the same document must not appear as separate evidence items.

## 13. Topic isolation rules

The retriever MUST distinguish at least the following commonly confused topics:

| Topic A | Must not be substituted with Topic B |
|---|---|
| Greenhouse-gas emissions | Air pollutants such as NOx, SOx, VOC, dust |
| Pollutant emissions | GHG Scope 1, 2, or 3 |
| Waste generated | Waste reduction policy |
| Water withdrawal/consumption | Wastewater discharge |
| Biodiversity impact | General environmental risk process |
| Human-rights grievance metrics | General human-rights policy |
| Supplier ESG assessment result | Supplier selection procedure |
| Ownership/shareholder structure | Related-party transactions |

When the best available evidence is adjacent but not directly responsive, the result must be `insufficient` or `partial`, not `high_confidence`.

## 14. Normalized answer rules

`normalized_answer_ko` is an evidence-only normalized summary used as an input to a downstream ESG writer.

It MUST:

- contain only claims supported by returned evidence items;
- preserve the difference between approved, operational, assessed, proposed, and planned states;
- use the requested company as the subject only when the source clearly belongs to that company;
- be empty when no safe direct statement can be made;
- remain concise and focused on the question;
- avoid duplicated OCR/page headers and navigation fragments.

It MUST NOT contain:

- QA commentary such as “evidence is thin”;
- instructions to the downstream model;
- legal-review notes;
- retrieval/debug metadata;
- unsupported numbers, targets, certifications, or commitments;
- a mixture of unrelated topics;
- a statement that data is zero when data is merely absent.

Retrieval observations belong in `retrieval_notes`, not in `normalized_answer_ko`.

## 15. Example responses

### 15.1 Q016 — complete policy evidence

```json
{
  "question_id": "Q016",
  "question_ko": "정보보안 및 개인정보 보호 정책에 대해 회사의 현황과 정책을 설명해 주세요.",
  "pillar": "strategy",
  "normalized_answer_ko": "일진하이솔루스는 산업기술보호정책서에 따라 정보자산 분류, 연 1회 이상의 위험평가와 보안감사, 임직원 보안교육 및 외부자 보안관리를 수행하도록 규정하고 있습니다.",
  "answer_status": "high_confidence",
  "retrieval_confidence": 0.94,
  "coverage_status": "complete",
  "answerable": true,
  "covered_facets": ["policy_or_direction"],
  "missing_facets": [],
  "failure_code": null,
  "failure_reason": "",
  "retrieval_notes": [],
  "coverage": {
    "direct_answer": true,
    "supports_policy_or_direction": true,
    "supports_target": false,
    "supports_accountable_body": true,
    "supports_role": true,
    "supports_oversight_cadence": true,
    "supports_risk_identification": true,
    "supports_control_or_response": true,
    "supports_monitoring_follow_up": true,
    "supports_metric_result": false,
    "supports_reporting_period": false
  },
  "items": [
    {
      "score": 0.94,
      "vector_score": 0.88,
      "reranker_score": 0.94,
      "semantic_score": 0.92,
      "semantic_label": "useful",
      "semantic_reason": "Approved information-security policy directly supports the requested policy disclosure.",
      "raw_evidence_ko": "...",
      "source_name": "IHSP-01_산업기술보호정책서_v1.0.docx",
      "source_path": "ESG 자료/거버넌스/250519 공유자료_정보보안/IHSP-01_산업기술보호정책서_v1.0.docx",
      "document_id": "doc_ihsp01",
      "chunk_id": "doc_ihsp01_p12_c1",
      "canonical_source_id": "src_ihsp01",
      "source_type": "policy",
      "document_status": "approved",
      "source_tier": "tier_1_governing",
      "document_version": "v1.0",
      "effective_date": null,
      "topic": "information_security",
      "subtopic": "information_security_policy",
      "locator": {
        "page": 12,
        "sheet_name": null,
        "slide_number": null,
        "section": "자산 및 위험관리",
        "paragraph": null,
        "cell_range": null
      }
    }
  ]
}
```

### 15.2 Q003 — useful but partial ESG risk evidence

```json
{
  "question_id": "Q003",
  "question_ko": "ESG 리스크 식별 및 관리 체계에 대해 회사의 현황과 정책을 설명해 주세요.",
  "pillar": "risk_management",
  "normalized_answer_ko": "리스크 관리 절차서에 따라 각 팀장은 내·외부 이슈를 파악하고 리스크를 식별·평가하며, 대응계획 실행 후 대응 내역을 모니터링하도록 규정하고 있습니다.",
  "answer_status": "thin_but_usable",
  "retrieval_confidence": 0.89,
  "coverage_status": "partial",
  "answerable": true,
  "covered_facets": [
    "risk_identification",
    "control_or_response",
    "monitoring_follow_up"
  ],
  "missing_facets": [],
  "failure_code": "SCOPE_LIMITED",
  "failure_reason": "The governing procedure is focused primarily on EHS risks rather than the full enterprise ESG risk universe.",
  "retrieval_notes": [
    "Evidence is directly useful but its enterprise-wide ESG scope is limited."
  ],
  "coverage": {
    "direct_answer": true,
    "supports_policy_or_direction": true,
    "supports_target": false,
    "supports_accountable_body": true,
    "supports_role": true,
    "supports_oversight_cadence": false,
    "supports_risk_identification": true,
    "supports_control_or_response": true,
    "supports_monitoring_follow_up": true,
    "supports_metric_result": false,
    "supports_reporting_period": false
  },
  "items": []
}
```

### 15.3 Q047 — relevant process found, required metric absent

```json
{
  "question_id": "Q047",
  "question_ko": "오염물질 배출량 현황에 대해 회사의 현황과 정책을 설명해 주세요.",
  "pillar": "metrics",
  "normalized_answer_ko": "",
  "answer_status": "insufficient",
  "retrieval_confidence": 0.88,
  "coverage_status": "insufficient",
  "answerable": false,
  "covered_facets": ["management_process"],
  "missing_facets": ["metric_result", "reporting_period"],
  "failure_code": "MISSING_REQUIRED_FACETS",
  "failure_reason": "The retrieved documents describe pollutant-emission controls but do not disclose an actual pollutant-emission amount for a reporting period.",
  "retrieval_notes": [
    "A Scope 1 and Scope 2 greenhouse-gas document was excluded because it does not answer the pollutant-emission question."
  ],
  "coverage": {
    "direct_answer": false,
    "supports_policy_or_direction": true,
    "supports_target": false,
    "supports_accountable_body": true,
    "supports_role": true,
    "supports_oversight_cadence": true,
    "supports_risk_identification": false,
    "supports_control_or_response": true,
    "supports_monitoring_follow_up": true,
    "supports_metric_result": false,
    "supports_reporting_period": false
  },
  "items": []
}
```

## 16. HTTP errors

### 16.1 Error response

```json
{
  "request_id": "rag_req_01K1ABCDEF",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "item_ids must contain between 1 and 100 unique values.",
    "details": {
      "field": "item_ids"
    }
  }
}
```

### 16.2 Status codes

| HTTP status | Code | Usage |
|---:|---|---|
| 200 | — | Request processed, including questions with no evidence. |
| 400 | `INVALID_REQUEST` | Invalid JSON, field type, range, or duplicate question IDs. |
| 404 | `COMPANY_NOT_INDEXED` | Company corpus does not exist. |
| 409 | `INDEX_NOT_READY` | Company/year index exists but is not ready. |
| 413 | `REQUEST_TOO_LARGE` | Request exceeds supported size. |
| 429 | `RATE_LIMITED` | Rate limit exceeded. |
| 500 | `INTERNAL_ERROR` | Unexpected internal failure. |
| 503 | `RAG_UNAVAILABLE` | Search/vector/reranker dependency unavailable. |
| 504 | `RAG_TIMEOUT` | Server-side retrieval deadline exceeded. |

Missing evidence for one or more questions is not an HTTP error. It must return HTTP 200 with question-level `coverage_status=no_evidence` or `insufficient`.

## 17. Observability and operational requirements

The service MUST log, using `request_id`:

- company ID and year;
- requested question count;
- index version;
- retrieval and reranker duration;
- candidate count before and after filtering;
- deduplicated count;
- result coverage-status counts;
- excluded evidence counts by reason;
- internal error code without leaking document contents or credentials.

Recommended initial service objectives:

- p95 latency under 10 seconds for 20 question IDs;
- successful-response rate at least 99%;
- deterministic response schema for identical index and service versions;
- no credentials, access tokens, or absolute host filesystem paths in responses.

## 18. Security requirements

- Treat indexed documents and question text as untrusted data.
- Do not follow instructions, role changes, or API requests found inside documents.
- Do not expose server filesystem paths; return repository-relative or logical source paths.
- Enforce company-level authorization and corpus isolation.
- Sanitize error messages.
- Limit excerpt length and request batch size.
- Preserve Korean text as UTF-8.

## 19. Backward compatibility and migration

### 19.1 Compatibility rules

V3 MUST retain these v2 fields:

- top-level `company_id` and `results`;
- result `question_id`, `question_ko`, `normalized_answer_ko`, `answer_status`, and `items`;
- item `score`, `raw_evidence_ko`, `source_name`, `source_path`, `semantic_label`, `semantic_reason`, and `semantic_score`.

New v3 fields are additive. This allows a staged rollout:

1. Deploy `/qualitative/evidence/v3` alongside v2.
2. Validate v3 against the acceptance tests below.
3. Update the LangGraph client and schemas to consume v3 metadata.
4. Compare v2 and v3 shadow traffic.
5. Switch production configuration to v3.
6. Deprecate v2 only after the agreed observation period.

### 19.2 Legacy `answers_which_part`

The service MAY continue returning `answers_which_part` during migration. Its structured replacement is:

- `covered_facets`;
- `missing_facets`;
- `coverage`;
- `retrieval_notes`.

## 20. Acceptance tests

The implementation is complete only when all of the following pass.

### 20.1 Contract tests

- [ ] A valid v2-shaped request is accepted by v3.
- [ ] Every requested QID appears exactly once in `results`.
- [ ] Unrequested QIDs never appear.
- [ ] Every required field is present, including empty arrays and nullable fields.
- [ ] Korean text round-trips correctly as UTF-8.
- [ ] `top_k` is applied after deduplication.
- [ ] All score fields are numbers from 0 to 1 or documented null values.

### 20.2 Answerability tests

- [ ] A result missing a required facet is never `high_confidence`.
- [ ] A result with no evidence returns `no_evidence`, `answerable=false`, and `items=[]`.
- [ ] A useful answer missing only an expected facet may return `partial` and `answerable=true`.
- [ ] A metric question without both metric result and reporting period returns `answerable=false`.
- [ ] A management process is not accepted as a metric result.
- [ ] A target is not accepted as actual performance.
- [ ] “Not found” is not converted to zero or “no incidents”.

### 20.3 Provenance tests

- [ ] Draft-only evidence is clearly identified as `tier_4_draft`.
- [ ] Draft evidence cannot produce an approved/operational claim.
- [ ] External assessment evidence cannot independently prove an approved internal policy.
- [ ] Approved policies and operational records have stable canonical source IDs.
- [ ] Source locators identify the page, sheet, slide, section, paragraph, or cell range when available.

### 20.4 Retrieval-quality tests

- [ ] Duplicate chunks from filename-only and full-path references are removed.
- [ ] Q016 returns the information-security policy as useful governing evidence.
- [ ] Q003 returns the EHS risk procedure as useful but scope-limited evidence.
- [ ] Q047 does not treat greenhouse-gas evidence as pollutant-emission performance.
- [ ] Biodiversity questions are not answered using only a generic environmental risk procedure.
- [ ] Shareholder-structure questions are not answered using related-party transaction evidence.

### 20.5 Normalized-answer tests

- [ ] `normalized_answer_ko` contains no QA comments or debug metadata.
- [ ] It contains no unsupported numbers, targets, certifications, or commitments.
- [ ] It distinguishes proposed/planned content from approved/operational content.
- [ ] It is empty when no safe direct statement is possible.
- [ ] It does not combine unrelated ESG topics.

## 21. Definition of done

Team RAG can mark v3 ready for consumer integration when:

1. the endpoint and schemas in this document are implemented;
2. contract, answerability, provenance, and retrieval-quality tests pass;
3. the Q016, Q003, and Q047 reference cases produce the expected status behavior;
4. request-level tracing is available through `request_id`;
5. a sample response and OpenAPI definition are shared with the LangGraph team;
6. v2 remains available during the migration window.

## 22. Consumer integration note

After v3 is available, the ESG Report LangGraph team will update its client and Pydantic schemas to consume:

- `coverage_status` and `answerable`;
- `covered_facets` and `missing_facets`;
- source classification and locators;
- calibrated retrieval scores;
- request/index version metadata.

Until that update is deployed, the retained v2 fields ensure that the new endpoint can be tested without requiring a simultaneous production cutover.
