"""Agent_Creator system prompt builder (T09)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CreatorPromptInput:
    objective_snippet: str
    step_intent: str
    boundary_block: str
    interface_snippets: str
    rag_snippets: str
    target_files: list[str]


def build_creator_prompt(inp: CreatorPromptInput) -> str:
    files = ", ".join(inp.target_files)
    return (
        "You are Agent_Creator (Composer). Implement the feature to the provided schema.\n"
        "You are FORBIDDEN from running tests or judging your own work. Write, save, exit.\n\n"
        f"## Objective\n{inp.objective_snippet}\n\n"
        f"## Task\n{inp.step_intent}\n\n"
        f"## Authorization\n{inp.boundary_block}\n\n"
        f"## Target files\n{files}\n\n"
        f"## Imported interfaces (do not invent methods)\n{inp.interface_snippets or '(none)'}\n\n"
        f"## RAG context\n{inp.rag_snippets or '(none)'}\n"
    )
