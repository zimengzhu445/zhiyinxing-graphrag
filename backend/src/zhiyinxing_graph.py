import re

from langchain_community.graphs.graph_document import Node, Relationship


CORE_TYPES = {"岗位", "任务", "能力", "能力单元", "技能", "知识"}
TECH_ALIASES = {
    "ai": "AI", "python": "Python", "rag": "RAG", "llm": "LLM",
    "fastapi": "FastAPI", "docker": "Docker", "k8s": "Kubernetes",
    "kubernetes": "Kubernetes", "rlhf": "RLHF", "multi-agent": "Multi-Agent",
    "multi agent": "Multi-Agent",
}
JOB_ALIASES = {
    "ai应用开发工程师": "人工智能应用开发工程师",
    "ai 应用开发工程师": "人工智能应用开发工程师",
    "人工智能应用开发": "人工智能应用开发工程师",
    "人工智能应用开发工程师": "人工智能应用开发工程师",
}


def normalize_name(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "").strip())
    value = value.replace("（", "(").replace("）", ")")
    value = re.sub(r"\s*([()])\s*", r"\1", value)
    lowered = value.lower()
    if lowered in JOB_ALIASES:
        return JOB_ALIASES[lowered]
    if lowered in TECH_ALIASES:
        return TECH_ALIASES[lowered]
    for alias, canonical in sorted(TECH_ALIASES.items(), key=lambda item: -len(item[0])):
        value = re.sub(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", canonical, value, flags=re.IGNORECASE)
    return value


def augment_graph_documents(graph_documents, industry_chain, professional_group, job_name):
    """Add Zhiyinxing context edges and task-evidenced job-to-ability closure."""
    if not graph_documents:
        return graph_documents
    industry_chain, professional_group, job_name = (
        normalize_name(industry_chain), normalize_name(professional_group), normalize_name(job_name)
    )
    if not (industry_chain and professional_group and job_name):
        return graph_documents
    nodes = {}
    for document in graph_documents:
        for node in document.nodes or []:
            nodes[(str(node.type), str(node.id))] = node

    def ensure_node(node_type, name):
        key = (node_type, name)
        if key not in nodes:
            nodes[key] = Node(id=name, type=node_type, properties={"name": name})
            graph_documents[0].nodes.append(nodes[key])
        return nodes[key]

    industry = ensure_node("产业链", industry_chain)
    group = ensure_node("岗位群", professional_group)
    job = ensure_node("岗位", job_name)
    existing = {
        (str(rel.source.id), str(rel.type), str(rel.target.id))
        for document in graph_documents for rel in (document.relationships or [])
    }

    def add_relation(source, rel_type, target):
        key = (str(source.id), rel_type, str(target.id))
        if key not in existing:
            graph_documents[0].relationships.append(
                Relationship(source=source, target=target, type=rel_type, properties={})
            )
            existing.add(key)

    add_relation(industry, "包含岗位群", group)
    add_relation(group, "包含岗位", job)
    for node in nodes.values():
        if str(node.type) == "任务":
            add_relation(job, "包含任务", node)
    task_abilities = {
        str(rel.target.id): rel.target
        for document in graph_documents for rel in (document.relationships or [])
        if str(rel.type) == "需要能力" and str(rel.source.type) == "任务" and str(rel.target.type) == "能力"
    }
    for ability in task_abilities.values():
        add_relation(job, "需要能力", ability)
    return graph_documents
