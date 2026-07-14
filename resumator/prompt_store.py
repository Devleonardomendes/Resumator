from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4


@dataclass
class Prompt:
    id: str
    name: str
    content: str
    updated_at: str
    system: bool = False
    protected: bool = False


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


DEFAULT_SELECTED_PROMPT_ID = ""
DEFAULT_PROMPTS: list[dict[str, str]] = []


def _read_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


class PromptStore:
    def __init__(self, path: Path):
        self.path = path
        self._prompts: list[Prompt] = []
        self.load()

    def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._prompts = self._default_prompts()
            self.save()
            return

        try:
            payload = _read_payload(self.path)
            payload_version = int(payload.get("version", 1))
            prompts = payload.get("prompts", [])
            self._prompts = []
            needs_save = payload_version < 3
            for item in prompts:
                if not isinstance(item, dict) or not item.get("name"):
                    continue

                content = str(item.get("content") or "")
                if not content:
                    continue

                self._prompts.append(
                    Prompt(
                        id=str(item["id"]),
                        name=str(item["name"]),
                        content=content,
                        updated_at=str(item.get("updated_at") or _now()),
                        system=bool(item.get("system", payload_version < 2)),
                        protected=False,
                    )
                )

            needs_save = self._dedupe_prompts() or needs_save
            if needs_save or any("system" not in item for item in prompts if isinstance(item, dict)):
                self.save()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            backup = self.path.with_suffix(".json.bak")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self._prompts = self._default_prompts()
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 3, "prompts": [self._to_payload(prompt) for prompt in self._prompts]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self) -> list[Prompt]:
        return sorted(self._prompts, key=lambda prompt: prompt.name.casefold())

    def get(self, prompt_id: str) -> Prompt | None:
        return next((prompt for prompt in self._prompts if prompt.id == prompt_id), None)

    def create(self, name: str, content: str, system: bool = False) -> Prompt:
        prompt = Prompt(
            id=str(uuid4()),
            name=name.strip(),
            content=content.strip(),
            updated_at=_now(),
            system=system,
            protected=False,
        )
        self._prompts.append(prompt)
        self.save()
        return prompt

    def update(self, prompt_id: str, name: str, content: str) -> Prompt:
        prompt = self.get(prompt_id)
        if prompt is None:
            raise KeyError(f"Prompt nÃ£o encontrado: {prompt_id}")
        prompt.name = name.strip()
        prompt.content = content.strip()
        prompt.updated_at = _now()
        prompt.protected = False
        self.save()
        return prompt

    def delete(self, prompt_id: str) -> None:
        prompt = self.get(prompt_id)
        if prompt is None:
            raise KeyError(f"Prompt nÃ£o encontrado: {prompt_id}")
        self._prompts = [prompt for prompt in self._prompts if prompt.id != prompt_id]
        self.save()

    def import_from_file(self, source_path: Path, system: bool = True) -> tuple[int, int]:
        payload = _read_payload(source_path)
        source_prompts = payload.get("prompts", [])
        existing_keys = {
            (prompt.name.strip().casefold(), prompt.content.strip())
            for prompt in self._prompts
        }
        existing_ids = {prompt.id for prompt in self._prompts}

        imported = 0
        skipped = 0
        for item in source_prompts:
            try:
                name = str(item["name"]).strip()
                content = str(item["content"]).strip()
            except (KeyError, TypeError):
                skipped += 1
                continue

            if not name or not content:
                skipped += 1
                continue

            key = (name.casefold(), content)
            if key in existing_keys:
                skipped += 1
                continue

            source_id = str(item.get("id") or uuid4())
            prompt_id = source_id if source_id not in existing_ids else str(uuid4())
            self._prompts.append(
                Prompt(
                    id=prompt_id,
                    name=name,
                    content=content,
                    updated_at=str(item.get("updated_at") or _now()),
                    system=system,
                    protected=False,
                )
            )
            existing_keys.add(key)
            existing_ids.add(prompt_id)
            imported += 1

        if imported:
            self._dedupe_prompts()
            self.save()
        return imported, skipped

    def export_user_prompts(self, output_path: Path) -> int:
        user_prompts = self.all()
        payload = {
            "version": 3,
            "source": "Resumator 11.3",
            "exported_at": _now(),
            "prompts": [asdict(prompt) for prompt in user_prompts],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(user_prompts)

    @staticmethod
    def _default_prompts() -> list[Prompt]:
        return [
            Prompt(
                id=item.get("id") or str(uuid4()),
                name=item["name"],
                content=item["content"],
                updated_at=_now(),
                system=True,
                protected=False,
            )
            for item in DEFAULT_PROMPTS
        ]

    def _dedupe_prompts(self) -> bool:
        selected_by_name: dict[str, Prompt] = {}
        for prompt in self._prompts:
            key = prompt.name.strip().casefold()
            existing = selected_by_name.get(key)
            if existing is None or self._is_preferred_duplicate(prompt, existing):
                selected_by_name[key] = prompt

        deduped: list[Prompt] = []
        seen: set[str] = set()
        for prompt in self._prompts:
            key = prompt.name.strip().casefold()
            if key in seen:
                continue
            deduped.append(selected_by_name[key])
            seen.add(key)

        changed = len(deduped) != len(self._prompts) or any(
            before is not after for before, after in zip(self._prompts, deduped)
        )
        self._prompts = deduped
        return changed

    @staticmethod
    def _is_preferred_duplicate(candidate: Prompt, current: Prompt) -> bool:
        if candidate.system != current.system:
            return candidate.system
        return candidate.updated_at > current.updated_at

    @staticmethod
    def _to_payload(prompt: Prompt) -> dict:
        payload = asdict(prompt)
        payload["protected"] = False
        return payload

