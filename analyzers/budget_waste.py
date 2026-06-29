# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Budget waste analyzer.

Detects components that consume context budget without contributing value:
  - Skills included in context but never appearing in ``skills_used``
  - Tools included in context but never appearing in ``tools_called``
  - Memory sections flagged by low-quality correlation (no runtime usage field
    available for memory, so we use a correlation heuristic instead)
"""

from __future__ import annotations

from dataclasses import dataclass

from ..loader import TurnRecord

_DEFAULT_UTILIZATION_THRESHOLD = 0.20  # below this → "rarely used"
_MIN_TURNS_FOR_WASTE_FLAG = 5           # don't flag components seen in fewer turns


@dataclass(frozen=True)
class ComponentUtilization:
    name: str
    component_type: str    # "skill" | "tool"
    times_included: int
    times_used: int
    utilization_rate: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "times_included": self.times_included,
            "times_used": self.times_used,
            "utilization_rate": round(self.utilization_rate, 4),
        }


@dataclass(frozen=True)
class BudgetWasteResult:
    never_used_skills: list[str]
    rarely_used_skills: list[ComponentUtilization]
    never_used_tools: list[str]
    rarely_used_tools: list[ComponentUtilization]
    potentially_wasteful_memory: list[str]  # memory sections in low-quality turns disproportionately

    def to_dict(self) -> dict:
        return {
            "never_used_skills": self.never_used_skills,
            "rarely_used_skills": [c.to_dict() for c in self.rarely_used_skills],
            "never_used_tools": self.never_used_tools,
            "rarely_used_tools": [c.to_dict() for c in self.rarely_used_tools],
            "potentially_wasteful_memory": self.potentially_wasteful_memory,
        }


class BudgetWasteAnalyzer:
    """Detect under-utilized components that waste context budget."""

    def __init__(
        self,
        turns: list[TurnRecord],
        qualities: list[float],
        utilization_threshold: float = _DEFAULT_UTILIZATION_THRESHOLD,
        min_turns: int = _MIN_TURNS_FOR_WASTE_FLAG,
    ) -> None:
        self._turns = turns
        self._qualities = qualities
        self._threshold = utilization_threshold
        self._min_turns = min_turns

    def analyze(self) -> BudgetWasteResult:
        skill_included: dict[str, int] = {}
        skill_used: dict[str, int] = {}
        tool_included: dict[str, int] = {}
        tool_called: dict[str, int] = {}

        global_mean = sum(self._qualities) / len(self._qualities) if self._qualities else 0.5

        # Memory heuristic: count how often each memory section appears in
        # low-quality turns vs. all turns
        memory_total: dict[str, int] = {}
        memory_low: dict[str, int] = {}

        for turn, quality in zip(self._turns, self._qualities):
            is_low = quality < global_mean - 0.1

            for s in turn.skills:
                skill_included[s] = skill_included.get(s, 0) + 1
            for s in turn.skills_used:
                skill_used[s] = skill_used.get(s, 0) + 1

            for t in turn.tools:
                tool_included[t] = tool_included.get(t, 0) + 1
            for t in turn.tools_called:
                tool_called[t] = tool_called.get(t, 0) + 1

            for m in turn.memory_sections:
                memory_total[m] = memory_total.get(m, 0) + 1
                if is_low:
                    memory_low[m] = memory_low.get(m, 0) + 1

        # Skills analysis
        never_used_skills: list[str] = []
        rarely_used_skills: list[ComponentUtilization] = []

        for skill, n_included in skill_included.items():
            if n_included < self._min_turns:
                continue
            n_used = skill_used.get(skill, 0)
            rate = n_used / n_included
            if n_used == 0:
                never_used_skills.append(skill)
            elif rate < self._threshold:
                rarely_used_skills.append(
                    ComponentUtilization(
                        name=skill,
                        component_type="skill",
                        times_included=n_included,
                        times_used=n_used,
                        utilization_rate=rate,
                    )
                )

        # Tools analysis
        never_used_tools: list[str] = []
        rarely_used_tools: list[ComponentUtilization] = []

        for tool, n_included in tool_included.items():
            if n_included < self._min_turns:
                continue
            n_called = tool_called.get(tool, 0)
            rate = n_called / n_included
            if n_called == 0:
                never_used_tools.append(tool)
            elif rate < self._threshold:
                rarely_used_tools.append(
                    ComponentUtilization(
                        name=tool,
                        component_type="tool",
                        times_included=n_included,
                        times_used=n_called,
                        utilization_rate=rate,
                    )
                )

        # Memory: flag sections where low-quality rate > 1.5× global low-quality rate
        total_turns = len(self._turns)
        global_low_rate = (
            sum(1 for q in self._qualities if q < global_mean - 0.1) / total_turns
            if total_turns
            else 0.0
        )
        potentially_wasteful_memory: list[str] = []
        for mem, total in memory_total.items():
            if total < self._min_turns:
                continue
            low = memory_low.get(mem, 0)
            low_rate = low / total
            if global_low_rate > 0 and low_rate > 1.5 * global_low_rate:
                potentially_wasteful_memory.append(mem)

        rarely_used_skills.sort(key=lambda c: c.utilization_rate)
        rarely_used_tools.sort(key=lambda c: c.utilization_rate)

        return BudgetWasteResult(
            never_used_skills=sorted(never_used_skills),
            rarely_used_skills=rarely_used_skills,
            never_used_tools=sorted(never_used_tools),
            rarely_used_tools=rarely_used_tools,
            potentially_wasteful_memory=sorted(potentially_wasteful_memory),
        )
