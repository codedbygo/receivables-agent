"""Versioned prompts from prompts/<name>/vN.md (prompt-registry). Only declared variables are
substituted; any other {{...}} (the drafting placeholders) passes through untouched."""

from dataclasses import dataclass
from functools import cache
from typing import Any

import yaml

from app.core.paths import find_up
from app.llm.gateway import PromptRef


@dataclass(frozen=True)
class Prompt:
    ref: PromptRef
    model: str
    max_tokens: int
    variables: tuple[dict[str, Any], ...]
    body: str

    def render(self, **values: str) -> str:
        out = self.body
        for var in self.variables:
            name = var["name"]
            if name not in values:
                if var.get("required"):
                    raise ValueError(f"prompt {self.ref.name}: variable {name} is required")
                values[name] = ""
            value = values[name]
            if "max_chars" in var and len(value) > var["max_chars"]:
                raise ValueError(f"prompt {self.ref.name}: {name} is over {var['max_chars']} characters")
            if "enum" in var and value not in var["enum"]:
                raise ValueError(f"prompt {self.ref.name}: {name} must be one of {var['enum']}")
            out = out.replace("{{" + name + "}}", value)
        return out


@cache
def load_prompt(name: str, version: int) -> Prompt:
    raw = (find_up("prompts") / name / f"v{version}.md").read_text(encoding="utf-8")
    _, front, body = raw.split("---\n", 2)
    meta = yaml.safe_load(front)
    return Prompt(
        PromptRef(meta["name"], int(meta["version"])),
        meta["model"],
        int(meta["max_tokens"]),
        tuple(meta.get("variables") or ()),
        body.strip() + "\n",
    )
