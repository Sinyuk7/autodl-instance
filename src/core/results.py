"""
Pipeline execution result types.
"""
from dataclasses import dataclass, field
from typing import Literal


IssueLevel = Literal["warning", "failure"]
PluginStatus = Literal["success", "skipped", "warning", "failure"]


@dataclass
class PipelineIssue:
    """A warning or failure produced by one pipeline plugin."""

    plugin: str
    message: str
    next_step: str = ""


@dataclass
class PluginResult:
    """Optional structured result returned by plugin lifecycle hooks."""

    status: PluginStatus
    message: str = ""
    next_step: str = ""

    @classmethod
    def success(cls, message: str = "") -> "PluginResult":
        return cls("success", message)

    @classmethod
    def skipped(cls, message: str = "") -> "PluginResult":
        return cls("skipped", message)

    @classmethod
    def warning(cls, message: str, next_step: str = "") -> "PluginResult":
        return cls("warning", message, next_step)

    @classmethod
    def failure(cls, message: str, next_step: str = "") -> "PluginResult":
        return cls("failure", message, next_step)


@dataclass
class PipelineResult:
    """Structured result for a lifecycle pipeline execution."""

    action: str
    failures: list[PipelineIssue] = field(default_factory=list)
    warnings: list[PipelineIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def add_failure(self, plugin: str, message: str, next_step: str = "") -> None:
        self.failures.append(PipelineIssue(plugin, message, next_step))

    def add_warning(self, plugin: str, message: str, next_step: str = "") -> None:
        self.warnings.append(PipelineIssue(plugin, message, next_step))

    def add_plugin_result(self, plugin: str, result: PluginResult | None) -> None:
        if result is None:
            return
        if result.status == "failure":
            self.add_failure(plugin, result.message, result.next_step)
        elif result.status == "warning":
            self.add_warning(plugin, result.message, result.next_step)
