"""Module contract + registry (see docs/MODULE_CONTRACT.md).

A :class:`Module` is the single plug-in surface: it boots services, contributes
tools to the orchestrator, exposes settings, and optionally provides a tab. The
:class:`ModuleRegistry` discovers ``modules/<id>/module.py`` (each defining
``get_module()``), starts them with a shared :class:`AppContext`, and collects
their tools.

In Phase 0/1 the Runner wires the built-in surfaces directly; this contract is
the foundation the orchestrator (Phase 2) and later modules build on.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

from .logsetup import get_logger

log = get_logger("registry")

CONTRACT_VERSION = "1.0"


# --------------------------------------------------------------------- data
@dataclass
class Tool:
    """An LLM-callable tool: an OpenAI function spec + a Python handler."""
    spec: dict
    handler: Callable[..., Any]
    risk: str = "read_only"  # read_only | safe_action | state_change | destructive

    @property
    def name(self) -> str:
        return self.spec.get("function", {}).get("name", "")


@dataclass
class SettingField:
    key: str
    label: str
    kind: str                         # bool | int | text | choice | secret
    default: Any = None
    choices: list = field(default_factory=list)


@dataclass
class AppContext:
    """Everything a module is allowed to depend on (never sibling modules)."""
    bus: Any
    db: Any
    paths: Any
    settings: Any                     # this module's ModuleSettings
    log: Any
    speak: Callable[[str], None] | None = None
    llm: Any = None


# ------------------------------------------------------------------- module
class Module:
    """Base class for a feature module. Override what you offer; all optional."""
    id: str = "module"
    name: str = "Module"
    version: str = "0.0.0"
    requires: list[str] = []
    min_contract: str = "1.0"

    def start(self, ctx: AppContext) -> None: ...
    def stop(self) -> None: ...

    def tools(self) -> list[Tool]:
        return []

    def settings_schema(self) -> list[SettingField]:
        return []

    def tab(self):
        return None

    def settings_widget(self):
        return None

    def subscribe(self, bus) -> None: ...


# ----------------------------------------------------------------- registry
class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}
        self._started: list[Module] = []

    # -- discovery --------------------------------------------------------
    def discover(self, package: str = "jarvis.modules") -> None:
        """Import every ``modules/<id>/module.py`` exposing ``get_module()``."""
        try:
            pkg = importlib.import_module(package)
        except ImportError:
            log.warning("No modules package %s", package)
            return
        for info in pkgutil.iter_modules(pkg.__path__):
            mod_path = f"{package}.{info.name}.module"
            try:
                m = importlib.import_module(mod_path)
            except ModuleNotFoundError:
                continue  # module without a module.py (fine in early phases)
            except Exception:
                log.exception("Failed importing %s", mod_path)
                continue
            factory = getattr(m, "get_module", None)
            if factory is None:
                continue
            try:
                self.add(factory())
            except Exception:
                log.exception("get_module() failed for %s", mod_path)

    def add(self, module: Module) -> None:
        if module.min_contract > CONTRACT_VERSION:
            log.warning("Skipping %s: needs contract %s > %s",
                        module.id, module.min_contract, CONTRACT_VERSION)
            return
        self._modules[module.id] = module
        log.info("Registered module %s v%s", module.id, module.version)

    # -- lifecycle --------------------------------------------------------
    def start_all(self, make_ctx: Callable[[Module], AppContext]) -> None:
        for module in self._ordered():
            try:
                module.start(make_ctx(module))
                module.subscribe(make_ctx(module).bus)
                self._started.append(module)
            except Exception:
                log.exception("Module %s failed to start; skipping", module.id)

    def stop_all(self) -> None:
        for module in reversed(self._started):
            try:
                module.stop()
            except Exception:
                log.exception("Module %s failed to stop", module.id)
        self._started.clear()

    def _ordered(self) -> list[Module]:
        """Topological-ish order honouring ``requires`` (best effort)."""
        ordered: list[Module] = []
        seen: set[str] = set()

        def visit(m: Module) -> None:
            if m.id in seen:
                return
            seen.add(m.id)
            for dep in m.requires:
                if dep in self._modules:
                    visit(self._modules[dep])
            ordered.append(m)

        for m in self._modules.values():
            visit(m)
        return ordered

    # -- queries ----------------------------------------------------------
    def modules(self) -> list[Module]:
        return list(self._modules.values())

    def all_tools(self) -> list[Tool]:
        tools: list[Tool] = []
        for m in self._started or self._modules.values():
            tools.extend(m.tools())
        return tools
