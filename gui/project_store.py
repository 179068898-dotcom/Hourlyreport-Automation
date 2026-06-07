from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modules.project_config import list_projects


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    project_name: str
    path: str

    @property
    def label(self) -> str:
        return f"{self.project_name} ({self.project_id})"


def load_project_summaries(root: str | Path) -> list[ProjectSummary]:
    projects = list_projects(root)
    return [
        ProjectSummary(
            project_id=str(item.get("project_id") or ""),
            project_name=str(item.get("project_name") or ""),
            path=str(item.get("path") or ""),
        )
        for item in projects
        if item.get("project_id")
    ]
