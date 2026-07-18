"""Standalone homepage teacher agent library.

This package is intentionally separate from ``crawler/pipline``.  The old
pipeline can be replaced later, after this agent is tested independently.
"""

from .agent import build_agent
from .config import AgentConfig
from .tools import AgentTools

__all__ = ["AgentConfig", "AgentTools", "build_agent"]
