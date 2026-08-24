"""Carga de política de lint por base de conocimiento (config/lint/<slug>.yaml)."""

import os

import yaml

DEFAULT_POLICY = {
    "scope": [],
    "counts": [],
    "index_max_entries": 20,
    "reachability_max_hops": 3,
    "thresholds": {"fail_on": "error"},
    "comment_checks": ["broken-link", "stale", "uncited-source", "scope", "count"],
}


def load_policy(kb_slug: str, config_dir: str) -> dict:
    policy = {**DEFAULT_POLICY}
    path = os.path.join(config_dir, f"{kb_slug}.yaml")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        policy.update(data)
        # merge de thresholds sin perder defaults
        policy["thresholds"] = {
            **DEFAULT_POLICY["thresholds"],
            **(data.get("thresholds") or {}),
        }
    return policy
