"""Readable LangGraph node names for the ESG qualitative workflow."""


class ESGGraphNodes:
    COMPANY_INTAKE = "01 Normalize Company Input"
    TEMPLATE_SELECTION = "02 Select Reporting Template"
    QUESTION_PLANNING = "03 Plan Disclosure Questions"
    RAG_EVIDENCE_RETRIEVAL = "04 Retrieve RAG Evidence"
    EVIDENCE_ELIGIBILITY = "05 Evaluate Evidence Eligibility"
    EVIDENCE_NORMALIZATION = "06 Normalize Evidence Sources"
    QUANTITATIVE_PROCESSING = "06B Process Quantitative Metrics"
    SKILL_SELECTION = "07 Select Specialist Skill"
    SKILL_CONTEXT = "08 Build Specialist Context"
    ANSWER_DRAFTING = "09 Draft Evidence-Grounded Answers"
    DRAFT_REVIEW = "10 Review Draft Grounding"
    SEMANTIC_REVIEW = "10B Review Semantic Completeness"
    ANSWER_REVISION = "11 Revise Review Failures"
    OUTPUT_HYGIENE = "11B Normalize Final Answer Output"
    REPORT_ASSEMBLY = "12 Assemble Report Output"
