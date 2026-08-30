"""Read-only audit for a job capability subgraph."""

import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List

from src.graph_query import get_graphDB_driver
from src.job_graph_query import JobNotFoundError


DOMAIN_LABELS = {
    "产业链": ("产业链", "IndustryChain"),
    "岗位群": ("岗位群", "JobGroup"),
    "岗位": ("岗位", "Job"),
    "任务": ("任务", "Task"),
    "能力": ("能力", "Ability"),
    "能力单元": ("能力单元", "AbilityUnit"),
    "技能": ("技能", "Skill"),
    "知识": ("知识", "Knowledge"),
}
SHARE_CHECK_TYPES = {"任务", "能力", "能力单元", "技能", "知识"}
DOMAIN_RELATIONSHIPS = "`包含任务`|`需要能力`|`包含能力单元`|`需要技能`|`需要知识`"


# This module intentionally has only read-only Cypher: MATCH / OPTIONAL MATCH / RETURN.
# The first query captures only the target job's upstream/downstream domain paths.
JOB_SUBGRAPH_AUDIT_QUERY = f"""
MATCH (job)
WHERE any(label IN labels(job) WHERE label IN ['岗位', 'Job'])
  AND toString(coalesce(job.name, job.id)) = $job_name
OPTIONAL MATCH upstream_path =
  (industry)-[:`包含岗位群`]->(group)-[:`包含岗位`]->(job)
WHERE any(label IN labels(industry) WHERE label IN ['产业链', 'IndustryChain'])
  AND any(label IN labels(group) WHERE label IN ['岗位群', 'JobGroup'])
OPTIONAL MATCH downstream_path =
  (job)-[:{DOMAIN_RELATIONSHIPS}*0..4]->(downstream_node)
WHERE all(node IN nodes(downstream_path) WHERE
  any(label IN labels(node) WHERE label IN
    ['岗位', 'Job', '任务', 'Task', '能力', 'Ability',
     '能力单元', 'AbilityUnit', '技能', 'Skill', '知识', 'Knowledge']))
RETURN job, collect(DISTINCT upstream_path) AS upstream_paths,
       collect(DISTINCT downstream_path) AS downstream_paths
"""

# This query is run only for the candidate Task/Ability/AbilityUnit/Skill/Knowledge
# nodes found above. It reports other jobs that reach the same node through the
# supported job-capability relationships; it does not update anything.
SHARED_JOB_REFERENCE_QUERY = f"""
UNWIND $node_ids AS node_id
MATCH (candidate)
WHERE elementId(candidate) = node_id
OPTIONAL MATCH (other_job)
WHERE any(label IN labels(other_job) WHERE label IN ['岗位', 'Job'])
  AND elementId(other_job) <> $target_job_id
  AND EXISTS {{
    MATCH (other_job)-[:{DOMAIN_RELATIONSHIPS}*1..4]->(candidate)
  }}
RETURN elementId(candidate) AS node_id,
       collect(DISTINCT coalesce(other_job.name, other_job.id)) AS other_job_names
"""

# GraphRAG nodes are not audit candidates. These flags merely state whether any
# of them are directly related to the requested job.
GRAPHRAG_ASSOCIATION_QUERY = """
MATCH (job)
WHERE elementId(job) = $job_id
OPTIONAL MATCH (job)-[]-(document:Document)
OPTIONAL MATCH (job)-[]-(chunk:Chunk)
OPTIONAL MATCH (job)-[]-(community:Community)
RETURN count(DISTINCT document) > 0 AS has_related_document,
       count(DISTINCT chunk) > 0 AS has_related_chunk,
       count(DISTINCT community) > 0 AS has_related_community
"""


def _node_type(labels: Iterable[str]) -> str:
    label_set = {str(label) for label in labels}
    for type_name, aliases in DOMAIN_LABELS.items():
        if label_set.intersection(aliases):
            return type_name
    return "其他"


def _node_payload(node: Any) -> Dict[str, Any]:
    properties = dict(node)
    return {
        "id": str(getattr(node, "element_id", "") or ""),
        "name": str(properties.get("name") or properties.get("id") or ""),
        "labels": sorted(str(label) for label in getattr(node, "labels", [])),
        "type": _node_type(getattr(node, "labels", [])),
    }


def _append_path_entities(path: Any, nodes: Dict[str, Dict[str, Any]], relationships: set) -> None:
    if path is None:
        return
    for node in path.nodes:
        payload = _node_payload(node)
        if payload["id"]:
            nodes[payload["id"]] = payload
    for rel in path.relationships:
        relationships.add(
            (
                str(getattr(rel.start_node, "element_id", "") or ""),
                str(rel.type),
                str(getattr(rel.end_node, "element_id", "") or ""),
            )
        )


def _append_node(node: Any, nodes: Dict[str, Dict[str, Any]]) -> None:
    if node is None:
        return
    payload = _node_payload(node)
    if payload["id"]:
        nodes[payload["id"]] = payload


def audit_job_graph(credentials: Any, job_name: str) -> Dict[str, Any]:
    """Return a read-only inventory and cross-job reuse audit for one job."""
    driver = None
    try:
        driver = get_graphDB_driver(credentials)
        if driver is None:
            raise RuntimeError("Unable to create Neo4j driver")
        records, _, _ = driver.execute_query(
            JOB_SUBGRAPH_AUDIT_QUERY,
            job_name=job_name,
            database_=credentials.database,
        )
        if not records:
            raise JobNotFoundError(job_name)

        record = records[0]
        nodes: Dict[str, Dict[str, Any]] = {}
        relationships = set()
        _append_node(record["job"], nodes)
        for path in record.get("upstream_paths", []):
            _append_path_entities(path, nodes, relationships)
        for path in record.get("downstream_paths", []):
            _append_path_entities(path, nodes, relationships)

        audit_candidates = [
            node_id
            for node_id, node in nodes.items()
            if node["type"] in SHARE_CHECK_TYPES
        ]
        shared_jobs_by_node = defaultdict(list)
        if audit_candidates:
            shared_records, _, _ = driver.execute_query(
                SHARED_JOB_REFERENCE_QUERY,
                node_ids=audit_candidates,
                target_job_id=record["job"].element_id,
                database_=credentials.database,
            )
            for shared_record in shared_records:
                shared_jobs_by_node[str(shared_record["node_id"])] = sorted(
                    str(name)
                    for name in shared_record.get("other_job_names", [])
                    if name
                )

        graph_rag_records, _, _ = driver.execute_query(
            GRAPHRAG_ASSOCIATION_QUERY,
            job_id=record["job"].element_id,
            database_=credentials.database,
        )
        graph_rag_associations = dict(graph_rag_records[0]) if graph_rag_records else {}

        by_type: Dict[str, List[Dict[str, Any]]] = {
            "Job": [],
            "Task": [],
            "Ability": [],
            "AbilityUnit": [],
            "Skill": [],
            "Knowledge": [],
            "JobGroup": [],
            "IndustryChain": [],
        }
        response_key = {
            "岗位": "Job",
            "任务": "Task",
            "能力": "Ability",
            "能力单元": "AbilityUnit",
            "技能": "Skill",
            "知识": "Knowledge",
            "岗位群": "JobGroup",
            "产业链": "IndustryChain",
        }
        for node in sorted(nodes.values(), key=lambda item: (item["type"], item["name"], item["id"])):
            item = dict(node)
            if node["type"] in SHARE_CHECK_TYPES:
                other_jobs = shared_jobs_by_node[node["id"]]
                item["referenced_by_other_jobs"] = bool(other_jobs)
                item["other_job_names"] = other_jobs
            by_type[response_key[node["type"]]].append(item)

        return {
            "job_name": job_name,
            "job_exists": True,
            "related_node_count": len(nodes),
            "related_relationship_count": len(relationships),
            "node_counts_by_type": {key: len(value) for key, value in by_type.items()},
            "nodes_by_type": by_type,
            "related_graphrag_nodes": {
                "has_related_document": bool(graph_rag_associations.get("has_related_document")),
                "has_related_chunk": bool(graph_rag_associations.get("has_related_chunk")),
                "has_related_community": bool(graph_rag_associations.get("has_related_community")),
            },
        }
    except JobNotFoundError:
        raise
    except Exception:
        logging.exception("Failed to audit job graph for job_name=%s", job_name)
        raise
    finally:
        if driver is not None:
            driver.close()
