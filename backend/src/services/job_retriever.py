from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


EXPECTED_RECORDS = 13_959
CSV_RELATIVE_PATH = Path("data/job_core/final_ai_application_job_core.csv")
CSV_PATH = Path(__file__).resolve().parents[2] / CSV_RELATIVE_PATH

TITLE_FIELD = "招聘岗位"
DESCRIPTION_FIELD = "职位描述"
KEYWORDS_FIELD = "人工智能关键词"
MATCHED_KEYWORDS_FIELD = "matched_keywords"
COMPANY_FIELD = "企业名称"
CITY_FIELD = "工作城市"
YEAR_FIELD = "source_year"
FALLBACK_YEAR_FIELD = "招聘发布年份"
MIN_SALARY_FIELD = "最低月薪"
MAX_SALARY_FIELD = "最高月薪"
SOURCE_FILE_FIELD = "source_file"


@dataclass(frozen=True)
class JobRecord:
    row_index: int
    raw: dict[str, str]
    title: str
    description: str
    keywords: str
    matched_keywords: str
    company: str
    city: str
    year: int | None
    salary: str
    source_id: str
    search_text: str
    title_norm: str
    description_norm: str
    keyword_norm: str
    search_text_norm: str


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize(value: str) -> str:
    return re.sub(r"[\s\-_()（）【】\[\]<>《》:：,，;；/\\|]+", "", value or "").lower()


def _parse_year(*values: str) -> int | None:
    for value in values:
        match = re.search(r"(20\d{2}|19\d{2})", str(value or ""))
        if match:
            return int(match.group(1))
    return None


def _format_salary(row: dict[str, str]) -> str:
    low = _compact_text(row.get(MIN_SALARY_FIELD))
    high = _compact_text(row.get(MAX_SALARY_FIELD))
    if low and high:
        return f"{low}-{high}"
    return low or high


def _load_records() -> list[JobRecord]:
    if not CSV_PATH.exists():
        raise RuntimeError(f"Job core CSV not found: {CSV_RELATIVE_PATH.as_posix()}")

    records: list[JobRecord] = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row_index, row in enumerate(reader, start=1):
            title = _compact_text(row.get(TITLE_FIELD))
            description = _compact_text(row.get(DESCRIPTION_FIELD))
            keywords = _compact_text(row.get(KEYWORDS_FIELD))
            matched_keywords = _compact_text(row.get(MATCHED_KEYWORDS_FIELD))
            company = _compact_text(row.get(COMPANY_FIELD))
            city = _compact_text(row.get(CITY_FIELD))
            year = _parse_year(row.get(YEAR_FIELD, ""), row.get(FALLBACK_YEAR_FIELD, ""))
            source_file = _compact_text(row.get(SOURCE_FILE_FIELD))
            source_id = f"{source_file or 'job_core_csv'}#row-{row_index}"
            search_text = "\n".join([title, keywords, matched_keywords, description])
            title_norm = _normalize(title)
            description_norm = _normalize(description)
            keyword_norm = _normalize("\n".join([keywords, matched_keywords]))
            search_text_norm = _normalize(search_text)
            records.append(
                JobRecord(
                    row_index=row_index,
                    raw={key: _compact_text(value) for key, value in row.items()},
                    title=title,
                    description=description,
                    keywords=keywords,
                    matched_keywords=matched_keywords,
                    company=company,
                    city=city,
                    year=year,
                    salary=_format_salary(row),
                    source_id=source_id,
                    search_text=search_text,
                    title_norm=title_norm,
                    description_norm=description_norm,
                    keyword_norm=keyword_norm,
                    search_text_norm=search_text_norm,
                )
            )

    if len(records) != EXPECTED_RECORDS:
        raise RuntimeError(
            f"Job core CSV record count mismatch: expected {EXPECTED_RECORDS}, got {len(records)}"
        )

    print(f"[job-index] loaded {len(records)} records")
    return records


_RECORDS = _load_records()


SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["Python", "python"],
    "Java": ["Java", "java"],
    "C++": ["C++", "c++"],
    "SQL": ["SQL", "sql", "MySQL", "PostgreSQL", "数据库查询"],
    "数据分析": ["数据分析", "数据挖掘", "数据建模"],
    "数据预处理": ["数据预处理", "数据清洗", "特征工程", "数据处理"],
    "机器学习": ["机器学习", "Machine Learning", "ML算法"],
    "深度学习": ["深度学习", "Deep Learning"],
    "NLP": ["NLP", "自然语言处理", "文本处理", "文本分类", "中文分词"],
    "计算机视觉": ["计算机视觉", "图像识别", "图像处理", "视觉算法"],
    "OpenCV": ["OpenCV", "opencv"],
    "PyTorch": ["PyTorch", "pytorch", "torch"],
    "TensorFlow": ["TensorFlow", "tensorflow"],
    "大语言模型": ["大语言模型", "LLM", "AIGC", "生成式AI", "ChatGPT", "GPT"],
    "RAG": ["RAG", "检索增强", "检索增强生成", "知识库问答"],
    "Agent/智能体": ["Agent", "智能体", "多智能体"],
    "LangChain": ["LangChain", "langchain"],
    "Prompt工程": ["Prompt", "提示词", "提示工程"],
    "Embedding": ["Embedding", "embedding", "向量化", "文本向量"],
    "向量检索": ["向量检索", "相似度检索", "语义检索"],
    "向量数据库": ["向量数据库", "Milvus", "FAISS", "faiss", "Pinecone", "Chroma"],
    "知识图谱": ["知识图谱", "Neo4j", "neo4j", "图数据库"],
    "知识库": ["知识库", "知识库构建", "知识管理"],
    "FastAPI": ["FastAPI", "fastapi"],
    "Docker": ["Docker", "docker", "容器化", "容器"],
    "Kubernetes": ["Kubernetes", "kubernetes", "K8s", "k8s"],
    "MLOps": ["MLOps", "mlops", "模型运维"],
    "微服务": ["微服务", "服务拆分"],
    "模型部署": ["模型部署", "模型服务", "模型上线", "部署上线", "推理服务"],
    "API服务化": ["API服务", "接口服务", "服务化", "RESTful", "接口开发"],
    "系统测试": ["系统测试", "测试用例", "测试方案", "质量保障", "QA"],
    "接口测试": ["接口测试", "API测试"],
    "自动化测试": ["自动化测试", "测试自动化"],
}

SKILL_ALIAS_NORMS = {
    skill: [_normalize(alias) for alias in aliases if _normalize(alias)]
    for skill, aliases in SKILL_ALIASES.items()
}


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        normalized = _normalize(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(term)
    return deduped


Confidence = Literal["high", "medium", "low"]


def _query_profile(job_name: str) -> dict[str, Any]:
    lower_name = job_name.lower()
    normalized_name = _normalize(job_name)
    base_terms = [job_name]
    for suffix in ("应用开发工程师", "开发工程师", "工程师", "岗位"):
        if job_name.endswith(suffix):
            base_terms.append(job_name[: -len(suffix)])

    profile: dict[str, Any] = {
        "kind": "generic",
        "title_terms": list(base_terms),
        "core_terms": list(base_terms),
        "aux_terms": [],
        "generic_terms": ["Python", "机器学习", "深度学习", "NLP", "Java", "C++"],
    }

    if "rag" in lower_name or "检索增强" in job_name or "知识库" in job_name:
        profile.update(
            {
                "kind": "rag",
                "title_terms": base_terms + ["RAG", "知识库", "知识问答", "智能问答", "问答系统", "大模型应用", "NLP应用"],
                "core_terms": [
                    "RAG",
                    "检索增强",
                    "知识库问答",
                    "知识问答",
                    "智能问答",
                    "问答系统",
                    "知识库",
                    "向量数据库",
                    "向量检索",
                    "语义检索",
                    "Embedding",
                    "LangChain",
                    "LlamaIndex",
                    "大模型应用开发",
                    "大模型应用",
                ],
                "aux_terms": ["大语言模型", "LLM", "Prompt", "Agent", "NLP", "自然语言处理", "文本处理"],
            }
        )

    if "部署" in job_name or "运维" in job_name or "mlops" in lower_name:
        profile.update(
            {
                "kind": "deploy",
                "title_terms": base_terms + ["模型部署", "模型服务", "模型运维", "算法部署", "AI部署", "MLOps"],
                "core_terms": [
                    "模型部署",
                    "推理服务",
                    "模型服务",
                    "模型服务化",
                    "模型上线",
                    "Docker",
                    "Kubernetes",
                    "K8s",
                    "ONNX",
                    "TensorRT",
                    "TorchServe",
                    "Triton",
                    "FastAPI",
                    "云部署",
                    "MLOps",
                    "容器化",
                ],
                "aux_terms": ["微服务", "API服务", "接口服务", "Linux", "CI/CD", "运维", "高并发"],
            }
        )

    if "测试" in job_name or "qa" in lower_name:
        profile.update(
            {
                "kind": "test",
                "title_terms": base_terms + ["AI测试", "人工智能测试", "模型测试", "算法测试", "大模型测试", "测试工程师"],
                "core_terms": [
                    "AI测试",
                    "人工智能测试",
                    "模型测试",
                    "算法测试",
                    "大模型测试",
                    "LLM评测",
                    "模型评测",
                    "模型质量",
                    "安全评测",
                    "幻觉评测",
                    "准确率评测",
                    "benchmark",
                    "自动化测试",
                    "系统测试",
                    "接口测试",
                    "测试用例",
                    "质量保障",
                ],
                "aux_terms": ["缺陷", "测试平台", "测试工具", "测试报告", "性能测试", "稳定性"],
                "ai_context_terms": ["AI", "人工智能", "模型", "算法", "大模型", "LLM", "机器学习", "深度学习"],
            }
        )

    if profile["kind"] == "generic" and (
        "人工智能应用" in job_name or "ai应用" in normalized_name or "应用开发" in job_name
    ):
        profile.update(
            {
                "kind": "app",
                "title_terms": base_terms + ["人工智能应用", "AI应用", "大模型应用", "智能应用", "应用开发", "智能体开发"],
                "core_terms": [
                    "人工智能应用",
                    "AI应用",
                    "大模型应用",
                    "智能应用",
                    "应用开发",
                    "智能体",
                    "Agent",
                    "大语言模型",
                    "RAG",
                    "Prompt",
                ],
                "aux_terms": ["Python", "FastAPI", "LangChain", "知识库", "NLP", "接口开发", "业务系统"],
            }
        )

    for key in ("title_terms", "core_terms", "aux_terms", "generic_terms", "ai_context_terms"):
        profile[key] = _dedupe_terms(profile.get(key, []))
    return profile


def _contains(text: str, term: str) -> bool:
    return _normalize(term) in _normalize(text)


def _contains_norm(normalized_text: str, term: str) -> bool:
    normalized_term = _normalize(term)
    return bool(normalized_term and normalized_term in normalized_text)


def _term_hits(record: JobRecord, terms: list[str]) -> tuple[list[str], list[str], list[str]]:
    title_hits: list[str] = []
    keyword_hits: list[str] = []
    description_hits: list[str] = []
    for term in terms:
        if _contains_norm(record.title_norm, term):
            title_hits.append(term)
        if _contains_norm(record.keyword_norm, term):
            keyword_hits.append(term)
        if _contains_norm(record.description_norm, term):
            description_hits.append(term)
    return _dedupe_terms(title_hits), _dedupe_terms(keyword_hits), _dedupe_terms(description_hits)


def _has_ai_test_context(record: JobRecord, profile: dict[str, Any]) -> bool:
    return any(_contains_norm(record.search_text_norm, term) for term in profile.get("ai_context_terms", []))


def _confidence_for_match(
    profile: dict[str, Any],
    score: float,
    title_hits: list[str],
    core_hits: list[str],
    aux_hits: list[str],
    record: JobRecord,
) -> Confidence | None:
    kind = profile.get("kind")
    title_strong = bool(title_hits)
    core_count = len(core_hits)

    if kind == "rag":
        if title_strong and core_count >= 2 and score >= 12:
            return "high"
        if core_count >= 4 and score >= 12:
            return "high"
        if title_strong and core_count >= 1:
            return "medium"
        if core_count >= 2 and score >= 6:
            return "medium"
        if core_count >= 1:
            return "low"
        return None

    if kind == "deploy":
        if title_strong and core_count >= 2 and score >= 12:
            return "high"
        if core_count >= 4 and score >= 12:
            return "high"
        if title_strong and core_count >= 1:
            return "medium"
        if core_count >= 2 and score >= 7:
            return "medium"
        if core_count >= 1:
            return "low"
        return None

    if kind == "test":
        ai_specific = [
            "AI测试",
            "人工智能测试",
            "模型测试",
            "算法测试",
            "大模型测试",
            "LLM评测",
            "模型评测",
            "模型质量",
            "安全评测",
            "幻觉评测",
            "准确率评测",
            "benchmark",
        ]
        strong_single_evidence = [
            "AI测试",
            "人工智能测试",
            "模型测试",
            "算法测试",
            "大模型测试",
            "LLM评测",
            "模型评测",
            "安全评测",
            "幻觉评测",
            "准确率评测",
        ]
        has_ai_specific = any(_normalize(term) in {_normalize(hit) for hit in core_hits} for term in ai_specific)
        has_strong_single_evidence = any(
            _normalize(term) in {_normalize(hit) for hit in core_hits}
            for term in strong_single_evidence
        )
        has_ai_context = _has_ai_test_context(record, profile)
        if title_strong and has_ai_context and core_count >= 2 and score >= 12:
            return "high"
        if has_ai_specific and core_count >= 2 and score >= 10:
            return "high"
        if title_strong and has_ai_context and core_count >= 1:
            return "medium"
        if has_ai_specific and core_count >= 2 and has_ai_context and score >= 5:
            return "medium"
        if has_strong_single_evidence and has_ai_context and score >= 2.8:
            return "medium"
        if core_count >= 3 and has_ai_context and score >= 7:
            return "medium"
        if core_count >= 1 and (has_ai_context or aux_hits):
            return "low"
        return None

    if kind == "app":
        if title_strong and core_count >= 2 and score >= 12:
            return "high"
        if core_count >= 4 and score >= 12:
            return "high"
        if title_strong and core_count >= 1:
            return "medium"
        if core_count >= 2 and score >= 7:
            return "medium"
        if core_count >= 1:
            return "low"
        return None

    if title_strong and score >= 8:
        return "medium"
    if core_count >= 2 and score >= 6:
        return "medium"
    if core_count >= 1:
        return "low"
    return None


def _score_record(record: JobRecord, job_name: str, profile: dict[str, Any]) -> tuple[float, Confidence | None, list[str]]:
    query_norm = _normalize(job_name)
    title_terms = profile.get("title_terms", [])
    core_terms = profile.get("core_terms", [])
    aux_terms = profile.get("aux_terms", [])
    generic_terms = profile.get("generic_terms", [])

    score = 0.0
    matched_terms: list[str] = []

    if query_norm and query_norm in record.title_norm:
        score += 8
        matched_terms.append(job_name)

    title_hits, _, _ = _term_hits(record, title_terms)
    core_title_hits, core_keyword_hits, core_description_hits = _term_hits(record, core_terms)
    aux_title_hits, aux_keyword_hits, aux_description_hits = _term_hits(record, aux_terms)
    generic_title_hits, generic_keyword_hits, generic_description_hits = _term_hits(record, generic_terms)

    score += 5 * len(title_hits)
    score += 5 * len(core_title_hits)
    score += 3 * len(core_keyword_hits)
    score += 2 * len(core_description_hits)
    score += 1.5 * len(aux_title_hits)
    score += 1 * len(aux_keyword_hits)
    score += 0.5 * len(aux_description_hits)

    # 通用 AI 技能只能作为轻微排序因素，不能独立构成岗位命中。
    score += 0.2 * len(generic_title_hits + generic_keyword_hits + generic_description_hits)

    core_hits = _dedupe_terms(core_title_hits + core_keyword_hits + core_description_hits)
    aux_hits = _dedupe_terms(aux_title_hits + aux_keyword_hits + aux_description_hits)
    matched_terms = _dedupe_terms(matched_terms + title_hits + core_hits + aux_hits)
    confidence = _confidence_for_match(profile, score, title_hits + core_title_hits, core_hits, aux_hits, record)

    if confidence is None:
        return 0.0, None, []
    return round(score, 2), confidence, matched_terms


def _truncate(value: str, max_length: int = 520) -> str:
    value = _compact_text(value)
    if len(value) <= max_length:
        return value
    return value[:max_length].rstrip() + "..."


def _skill_counts(records: list[JobRecord]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for record in records:
        text = record.search_text_norm
        for skill, aliases in SKILL_ALIAS_NORMS.items():
            if any(alias in text for alias in aliases):
                counter[skill] += 1

    total = len(records) or 1
    return [
        {"name": skill, "count": count, "ratio": round(count / total, 4)}
        for skill, count in counter.most_common(20)
    ]


def get_job_data_status() -> dict[str, Any]:
    return {
        "loaded": True,
        "records": len(_RECORDS),
        "source": CSV_RELATIVE_PATH.name,
    }


def retrieve_job_evidence(job_name: str, limit: int = 100) -> dict[str, Any]:
    job_name = _compact_text(job_name)
    if not job_name:
        raise ValueError("jobName is required")

    limit = max(1, min(int(limit or 100), 300))
    profile = _query_profile(job_name)

    scored: list[tuple[float, Confidence, JobRecord, list[str]]] = []
    for record in _RECORDS:
        score, confidence, matched_terms = _score_record(record, job_name, profile)
        if confidence:
            scored.append((score, confidence, record, matched_terms))

    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    scored.sort(key=lambda item: (confidence_rank[item[1]], item[0], item[2].year or 0), reverse=True)
    official_scored = [item for item in scored if item[1] in {"high", "medium"}]
    official_records = [record for _, _, record, _ in official_scored]
    all_records = [record for _, _, record, _ in scored]
    returned = official_scored[:limit]
    returned_records = [record for _, _, record, _ in returned]

    confidence_counts = Counter(confidence for _, confidence, _, _ in scored)

    years = [record.year for record in official_records if record.year]
    year_distribution = {str(year): 0 for year in range(2016, 2027)}
    for year in years:
        if 2016 <= year <= 2026:
            year_distribution[str(year)] += 1

    matched_titles = Counter(record.title for record in official_records if record.title).most_common(20)

    samples = []
    for score, confidence, record, matched_terms in returned:
        samples.append(
            {
                "sourceId": record.source_id,
                "jobTitle": record.title,
                "year": record.year,
                "company": record.company,
                "city": record.city,
                "salary": record.salary,
                "text": _truncate(record.description),
                "matchedTerms": matched_terms[:12],
                "score": score,
                "confidence": confidence,
            }
        )

    return {
        "jobName": job_name,
        "totalRecords": len(_RECORDS),
        "matchedCount": len(official_scored),
        "highConfidenceCount": confidence_counts.get("high", 0),
        "mediumConfidenceCount": confidence_counts.get("medium", 0),
        "lowConfidenceCount": confidence_counts.get("low", 0),
        "returnedCount": len(returned_records),
        "yearRange": [min(years), max(years)] if years else [],
        "matchedJobTitles": [{"name": name, "count": count} for name, count in matched_titles],
        "topSkills": _skill_counts(official_records),
        "yearDistribution": year_distribution,
        "samples": samples,
        "lowConfidenceSamples": [
            {
                "sourceId": record.source_id,
                "jobTitle": record.title,
                "year": record.year,
                "company": record.company,
                "score": score,
                "confidence": confidence,
                "matchedTerms": matched_terms[:12],
                "text": _truncate(record.description),
            }
            for score, confidence, record, matched_terms in scored
            if confidence == "low"
        ][: min(20, limit)],
        "candidateCount": len(all_records),
        "source": "job_core_csv",
    }


def select_job_evidence_for_graph(job_name: str, limit: int = 50) -> dict[str, Any]:
    """Return full-text high/medium recruitment evidence for graph construction."""
    job_name = _compact_text(job_name)
    if not job_name:
        raise ValueError("jobName is required")

    limit = max(1, min(int(limit or 50), 100))
    profile = _query_profile(job_name)
    scored: list[tuple[float, Confidence, JobRecord, list[str]]] = []
    for record in _RECORDS:
        score, confidence, matched_terms = _score_record(record, job_name, profile)
        if confidence in {"high", "medium"}:
            scored.append((score, confidence, record, matched_terms))

    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    scored.sort(key=lambda item: (confidence_rank[item[1]], item[0], item[2].year or 0), reverse=True)

    selected: list[tuple[float, Confidence, JobRecord, list[str]]] = []
    title_counts: Counter[str] = Counter()
    year_counts: Counter[int] = Counter()
    seen_source_ids: set[str] = set()

    def add_candidate(item: tuple[float, Confidence, JobRecord, list[str]]) -> bool:
        _, _, record, _ = item
        if record.source_id in seen_source_ids:
            return False
        selected.append(item)
        seen_source_ids.add(record.source_id)
        title_counts[record.title] += 1
        if record.year:
            year_counts[record.year] += 1
        return True

    for item in scored:
        _, _, record, _ = item
        if len(selected) >= limit:
            break
        if title_counts[record.title] >= 3:
            continue
        if record.year and year_counts[record.year] >= 8:
            continue
        add_candidate(item)

    if len(selected) < limit:
        for item in scored:
            if len(selected) >= limit:
                break
            add_candidate(item)

    selected_records = [record for _, _, record, _ in selected]
    years = [record.year for record in selected_records if record.year]
    evidence = [
        {
            "sourceId": record.source_id,
            "jobTitle": record.title,
            "year": record.year,
            "company": record.company,
            "city": record.city,
            "salary": record.salary,
            "text": record.description,
            "matchedTerms": matched_terms[:12],
            "score": score,
            "confidence": confidence,
        }
        for score, confidence, record, matched_terms in selected
    ]
    return {
        "jobName": job_name,
        "matchedCount": len(scored),
        "usedCount": len(evidence),
        "yearRange": [min(years), max(years)] if years else [],
        "source": "job_core_csv",
        "evidence": evidence,
    }
