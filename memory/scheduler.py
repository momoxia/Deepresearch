"""
Task-aware memory injection for research workflows.
"""
import logging
import re

logger = logging.getLogger(__name__)

TASK_PATTERNS: dict[str, list[str]] = {
    "literature": [
        r"文献", r"论文", r"综述", r"citation|cite|paper",
        r"PubMed|arXiv|Google Scholar",
    ],
    "synthesis": [
        r"对比", r"总结", r"归纳", r"框架", r"综述", r"synthesize|compare",
    ],
    "fact_check": [
        r"核实", r"验证", r"是否准确", r"fact.?check", r"辟谣",
    ],
    "writing": [
        r"大纲", r"撰写", r"段落", r"报告", r"outline|draft",
    ],
    "chitchat": [],
}

STRATEGY_CONFIG: dict[str, dict] = {
    "literature": {
        "top_k": 25,
        "category_weights": {
            "semantic": 1.4,
            "procedural": 1.0,
            "preference": 0.9,
            "episodic": 0.6,
        },
        "require_categories": ["semantic"],
    },
    "synthesis": {
        "top_k": 30,
        "category_weights": {
            "semantic": 1.3,
            "episodic": 1.1,
            "procedural": 1.0,
            "preference": 0.8,
        },
        "require_categories": ["semantic", "episodic"],
    },
    "fact_check": {
        "top_k": 20,
        "category_weights": {
            "semantic": 1.5,
            "procedural": 0.8,
            "preference": 0.5,
            "episodic": 0.5,
        },
        "require_categories": ["semantic"],
    },
    "writing": {
        "top_k": 28,
        "category_weights": {
            "preference": 1.2,
            "semantic": 1.2,
            "procedural": 1.1,
            "episodic": 0.9,
        },
        "require_categories": [],
    },
    "chitchat": {
        "top_k": 10,
        "category_weights": {
            "preference": 1.2,
            "episodic": 1.0,
            "semantic": 0.6,
            "procedural": 0.4,
        },
        "require_categories": [],
    },
}


def detect_task_type(query: str) -> str:
    for task_type, patterns in TASK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug("Detected task type: %s (pattern: %s)", task_type, pattern)
                return task_type
    return "chitchat"


def get_strategy(task_type: str) -> dict:
    return STRATEGY_CONFIG.get(task_type, STRATEGY_CONFIG["chitchat"])
