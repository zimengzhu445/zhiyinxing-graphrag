"""Stable, domain-specific job capability subgraph query."""

import logging
from typing import Any, Dict, Iterable, List

from src.graph_query import get_graphDB_driver


class JobNotFoundError(Exception):
    """Raised when no job node matches the requested business name."""


_TYPE_LABELS = (
    ("产业链", "IndustryChain"),
    ("岗位群", "JobGroup"),
    ("岗位", "Job"),
    ("任务", "Task"),
    ("能力", "Ability"),
    ("能力单元", "AbilityUnit"),
    ("技能", "Skill"),
    ("知识", "Knowledge"),
    ("课程", "Course"),
    ("实训", "Training"),
    ("工具", "Tool"),
)


JOB_GRAPH_QUERY = """
MATCH (job)
WHERE any(label IN labels(job) WHERE label IN ['岗位', 'Job'])
  AND toString(coalesce(job.name, job.id)) = $job_name
OPTIONAL MATCH (industry)-[industry_group:`包含岗位群`]->(group)
WHERE any(label IN labels(industry) WHERE label IN ['产业链', 'IndustryChain'])
  AND any(label IN labels(group) WHERE label IN ['岗位群', 'JobGroup'])
  AND (group)-[:`包含岗位`]->(job)
OPTIONAL MATCH (job)-[job_task:`包含任务`]->(task)
WHERE any(label IN labels(task) WHERE label IN ['任务', 'Task'])
OPTIONAL MATCH (job)-[job_ability:`需要能力`]->(job_ability_node)
WHERE any(label IN labels(job_ability_node) WHERE label IN ['能力', 'Ability'])
OPTIONAL MATCH (task)-[task_ability:`需要能力`]->(task_ability_node)
WHERE any(label IN labels(task_ability_node) WHERE label IN ['能力', 'Ability'])
OPTIONAL MATCH (job_ability_node)-[ability_unit_rel:`包含能力单元`]->(unit)
WHERE any(label IN labels(unit) WHERE label IN ['能力单元', 'AbilityUnit'])
OPTIONAL MATCH (unit)-[skill_rel:`需要技能`]->(skill)
WHERE any(label IN labels(skill) WHERE label IN ['技能', 'Skill'])
OPTIONAL MATCH (unit)-[knowledge_rel:`需要知识`]->(knowledge)
WHERE any(label IN labels(knowledge) WHERE label IN ['知识', 'Knowledge'])
OPTIONAL MATCH (task_ability_node)-[task_unit_rel:`包含能力单元`]->(task_unit)
WHERE any(label IN labels(task_unit) WHERE label IN ['能力单元', 'AbilityUnit'])
OPTIONAL MATCH (task_unit)-[task_skill_rel:`需要技能`]->(task_skill)
WHERE any(label IN labels(task_skill) WHERE label IN ['技能', 'Skill'])
OPTIONAL MATCH (task_unit)-[task_knowledge_rel:`需要知识`]->(task_knowledge)
WHERE any(label IN labels(task_knowledge) WHERE label IN ['知识', 'Knowledge'])
RETURN
  job,
  collect(DISTINCT industry) AS industries,
  collect(DISTINCT group) AS groups,
  collect(DISTINCT task) AS tasks,
  collect(DISTINCT job_ability_node) + collect(DISTINCT task_ability_node) AS abilities,
  collect(DISTINCT unit) + collect(DISTINCT task_unit) AS units,
  collect(DISTINCT skill) + collect(DISTINCT task_skill) AS skills,
  collect(DISTINCT knowledge) + collect(DISTINCT task_knowledge) AS knowledge,
  collect(DISTINCT industry_group) + collect(DISTINCT job_task)
    + collect(DISTINCT job_ability) + collect(DISTINCT task_ability)
    + collect(DISTINCT ability_unit_rel) + collect(DISTINCT skill_rel)
    + collect(DISTINCT knowledge_rel) + collect(DISTINCT task_unit_rel)
    + collect(DISTINCT task_skill_rel) + collect(DISTINCT task_knowledge_rel)
    AS relationships
"""


def _node_type(labels: Iterable[str]) -> str:
    labels = {str(label) for label in labels}
    for chinese, english in _TYPE_LABELS:
        if chinese in labels:
            return chinese
        if english in labels:
            return chinese
    return next(iter(labels), "Node")


def _clean_properties(properties: Dict[str, Any]) -> Dict[str, Any]:
    return {
        str(key): value
        for key, value in (properties or {}).items()
        if key not in {"embedding", "text", "summary"}
    }


def _node_payload(node: Any) -> Dict[str, Any]:
    properties = dict(node)
    node_id = str(getattr(node, "element_id", "") or properties.get("id") or properties.get("name") or "")
    name = str(properties.get("name") or properties.get("id") or node_id)
    return {
        "id": node_id,
        "name": name,
        "type": _node_type(getattr(node, "labels", [])),
        "properties": _clean_properties(properties),
    }


def _relationship_payload(rel: Any) -> Dict[str, Any]:
    start = getattr(rel, "start_node", None)
    end = getattr(rel, "end_node", None)
    return {
        "source": str(getattr(start, "element_id", "") or ""),
        "target": str(getattr(end, "element_id", "") or ""),
        "type": str(getattr(rel, "type", "") or ""),
        "properties": _clean_properties(dict(rel)),
    }


def query_job_graph(credentials: Any, job_name: str) -> Dict[str, Any]:
    """Query and normalize the complete job capability subgraph from Neo4j."""
    driver = None
    try:
        driver = get_graphDB_driver(credentials)
        if driver is None:
            raise RuntimeError("Unable to create Neo4j driver")
        records, _, _ = driver.execute_query(
            JOB_GRAPH_QUERY,
            job_name=job_name,
            database_=credentials.database,
        )
        if not records:
            raise JobNotFoundError(job_name)

        record = records[0]
        category_nodes = {
            "industry_chain": record.get("industries", []),
            "job_group": record.get("groups", []),
            "tasks": record.get("tasks", []),
            "abilities": record.get("abilities", []),
            "ability_units": record.get("units", []),
            "skills": record.get("skills", []),
            "knowledge": record.get("knowledge", []),
        }
        raw_nodes = [record["job"]]
        for values in category_nodes.values():
            raw_nodes.extend(values or [])

        nodes: List[Dict[str, Any]] = []
        seen_nodes = set()
        for node in raw_nodes:
            if node is None:
                continue
            payload = _node_payload(node)
            if payload["id"] and payload["id"] not in seen_nodes:
                seen_nodes.add(payload["id"])
                nodes.append(payload)

        edges: List[Dict[str, Any]] = []
        seen_edges = set()
        for rel in record.get("relationships", []):
            if rel is None:
                continue
            payload = _relationship_payload(rel)
            key = (payload["source"], payload["type"], payload["target"])
            if payload["source"] and payload["target"] and key not in seen_edges:
                seen_edges.add(key)
                edges.append(payload)

        by_id = {node["id"]: node for node in nodes}
        grouped = {key: [] for key in category_nodes}
        for node in nodes:
            type_name = node["type"]
            for key, values in (
                ("industry_chain", ("产业链",)),
                ("job_group", ("岗位群",)),
                ("tasks", ("任务",)),
                ("abilities", ("能力",)),
                ("ability_units", ("能力单元",)),
                ("skills", ("技能",)),
                ("knowledge", ("知识",)),
            ):
                if type_name in values:
                    grouped[key].append(node)
        job = next((node for node in nodes if node["type"] == "岗位"), {})
        return {
            **grouped,
            "job": job,
            "nodes": nodes,
            "edges": edges,
        }
    except JobNotFoundError:
        raise
    except Exception:
        logging.exception("Failed to query job graph for job_name=%s", job_name)
        raise
    finally:
        if driver is not None:
            driver.close()
