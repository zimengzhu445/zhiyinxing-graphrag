from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.entities.source_extract_params import SourceScanExtractParams
from src.entities.source_node import sourceNode
from src.graphDB_dataAccess import graphDBdataAccess
from src.job_graph_query import query_job_graph
from src.main import create_graph_database_connection, extract_graph_from_file_local_file
from src.services.job_retriever import select_job_evidence_for_graph
from src.shared.common_fn import get_value_from_env


JOB_EVIDENCE_SCHEMA_INSTRUCTIONS = """
你正在基于真实招聘证据构建岗位能力子图。

只能依据输入中的招聘证据抽取，不要凭常识补充没有证据支持的技能、知识、任务或课程。

只允许抽取以下节点类型：
岗位、任务、能力、能力单元、技能、知识、课程。

只允许使用以下关系：
岗位-包含任务->任务
岗位-需要能力->能力
任务-需要能力->能力
能力-包含能力单元->能力单元
能力单元-需要技能->技能
能力单元-需要知识->知识
能力-关联课程->课程

抽取要求：
1. 岗位节点必须使用目标岗位名称，不要把招聘原始标题当作多个岗位节点。
2. 能力控制在 5-8 个，表示完成岗位工作的综合职业能力。
3. 技能控制在 8-15 个，必须来自招聘文本中明确出现或高度同义的技术/工具/工程实践。
4. 知识控制在 8-15 个，必须由证据中的概念、原理、方法支撑。
5. 任务控制在 4-8 个，必须是招聘证据中的真实工作活动。
6. 适度归并同义词：K8s 归并为 Kubernetes，LLM 归并为大语言模型，RAG 归并为检索增强生成。
7. 不要生成大量重复节点，总节点约 25-45 个。
8. 每条能力、技能、知识、任务都应能在招聘证据中找到依据。
"""

ALLOWED_JOB_EVIDENCE_NODES = "岗位,任务,能力,能力单元,技能,知识,课程"
ALLOWED_JOB_EVIDENCE_RELATIONSHIPS = (
    "岗位,包含任务,任务,"
    "岗位,需要能力,能力,"
    "任务,需要能力,能力,"
    "能力,包含能力单元,能力单元,"
    "能力单元,需要技能,技能,"
    "能力单元,需要知识,知识,"
    "能力,关联课程,课程"
)


def _safe_file_stem(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_.-]+", "-", value).strip("-")
    return safe[:80] or "job-evidence"


def _evidence_document_text(job_name: str, evidence: list[dict[str, Any]]) -> str:
    lines = [
        f"目标岗位：{job_name}",
        "数据来源：job_core_csv 真实核心招聘数据",
        f"证据数量：{len(evidence)}",
        "",
        "以下为用于构图的高质量招聘证据。请只依据这些证据抽取岗位能力图谱。",
        "",
    ]
    for index, item in enumerate(evidence, start=1):
        lines.extend(
            [
                f"【证据 {index}】",
                f"sourceId: {item.get('sourceId')}",
                f"jobTitle: {item.get('jobTitle')}",
                f"year: {item.get('year')}",
                f"company: {item.get('company')}",
                f"confidence: {item.get('confidence')}",
                f"score: {item.get('score')}",
                f"matchedTerms: {'、'.join(item.get('matchedTerms') or [])}",
                "text:",
                str(item.get("text") or ""),
                "",
            ]
        )
    return "\n".join(lines)


def _create_document_source(graph, file_name: str, file_path: Path, source_id: str, job_name: str, model: str) -> None:
    source = sourceNode()
    source.file_name = file_name
    source.file_size = file_path.stat().st_size
    source.file_type = "txt"
    source.file_source = "local file"
    source.created_at = datetime.now()
    source.model = model
    source.source_id = source_id
    source.source_type = "job_core_csv"
    source.source_title = f"JobEvidence招聘证据-{job_name}"
    graphDBdataAccess(graph).create_source_node(source)


def _apply_job_graph_provenance(
    graph,
    job_name: str,
    source_id: str,
    evidence_count: int,
    year_range: list[int],
) -> None:
    year_min = year_range[0] if year_range else None
    year_max = year_range[1] if len(year_range) > 1 else None
    graph.query(
        """
        MERGE (job:`岗位` {id: $job_name})
        SET job:Job:__Entity__,
            job.name = $job_name,
            job.source_type = "job_core_csv",
            job.source_job = $job_name,
            job.evidence_count = $evidence_count,
            job.year_min = $year_min,
            job.year_max = $year_max
        WITH job
        MATCH (n)
        WHERE n <> job
          AND any(ref IN coalesce(n.source_refs, []) WHERE ref = $source_id)
          AND (n:`任务` OR n:`能力` OR n:`能力单元` OR n:`技能` OR n:`知识` OR n:`课程`)
        SET n.source_type = "job_core_csv",
            n.source_job = $job_name,
            n.evidence_count = $evidence_count,
            n.year_min = $year_min,
            n.year_max = $year_max
        WITH job
        OPTIONAL MATCH (task:`任务`)
        WHERE any(ref IN coalesce(task.source_refs, []) WHERE ref = $source_id)
        FOREACH (_ IN CASE WHEN task IS NULL THEN [] ELSE [1] END |
          MERGE (job)-[r:`包含任务`]->(task)
          SET r.source_type = "job_core_csv",
              r.source_job = $job_name,
              r.evidence_count = $evidence_count
        )
        WITH job
        OPTIONAL MATCH (ability:`能力`)
        WHERE any(ref IN coalesce(ability.source_refs, []) WHERE ref = $source_id)
        FOREACH (_ IN CASE WHEN ability IS NULL THEN [] ELSE [1] END |
          MERGE (job)-[r:`需要能力`]->(ability)
          SET r.source_type = "job_core_csv",
              r.source_job = $job_name,
              r.evidence_count = $evidence_count
        )
        """,
        {
            "job_name": job_name,
            "source_id": source_id,
            "evidence_count": evidence_count,
            "year_min": year_min,
            "year_max": year_max,
        },
        session_params={"database": getattr(graph, "_database", None)},
    )


async def build_job_graph_from_evidence(
    credentials: Any,
    job_name: str,
    merged_dir: str,
    model: str = "deepseek_v4_flash",
    evidence_limit: int = 50,
) -> dict[str, Any]:
    selection = select_job_evidence_for_graph(job_name, evidence_limit)
    evidence = selection["evidence"]
    if not evidence:
        raise ValueError(f"No high/medium job evidence found for {job_name}")

    source_id = f"job_evidence::{job_name}"
    file_name = f"job-evidence-{_safe_file_stem(job_name)}.txt"
    merged_path = Path(merged_dir)
    merged_path.mkdir(parents=True, exist_ok=True)
    file_path = merged_path / file_name
    file_path.write_text(_evidence_document_text(job_name, evidence), encoding="utf-8")

    graph = create_graph_database_connection(credentials)
    _create_document_source(graph, file_name, file_path, source_id, job_name, model)

    params = SourceScanExtractParams(
        model=model,
        source_type="local file",
        source_metadata_type="job_core_csv",
        source_id=source_id,
        source_title=f"JobEvidence招聘证据-{job_name}",
        file_name=file_name,
        allowedNodes=ALLOWED_JOB_EVIDENCE_NODES,
        allowedRelationship=ALLOWED_JOB_EVIDENCE_RELATIONSHIPS,
        token_chunk_size=12000,
        chunk_overlap=0,
        chunks_to_combine=1,
        additional_instructions=f"""
        {JOB_EVIDENCE_SCHEMA_INSTRUCTIONS}

        目标岗位：{job_name}
        证据来源：13,959 条核心招聘数据中的 high / medium JobEvidence。
        本次输入证据数：{len(evidence)}
        """,
        embedding_provider=get_value_from_env("EMBEDDING_PROVIDER", "sentence-transformer", str),
        embedding_model=get_value_from_env("EMBEDDING_MODEL", "all-MiniLM-L6-v2", str),
        process_all_chunks=True,
        job_name=job_name,
    )

    await extract_graph_from_file_local_file(credentials, params, str(file_path))
    _apply_job_graph_provenance(
        graph,
        job_name,
        source_id,
        selection["usedCount"],
        selection["yearRange"],
    )
    graph_result = query_job_graph(credentials, job_name)
    return {
        "jobName": job_name,
        "evidence": {
            "matchedCount": selection["matchedCount"],
            "usedCount": selection["usedCount"],
            "yearRange": selection["yearRange"],
            "source": selection["source"],
        },
        "graph": {
            "nodes": graph_result.get("nodes", []),
            "edges": graph_result.get("edges", []),
        },
        "neo4j": {"written": True},
        "source": "job_evidence_graphrag",
    }
