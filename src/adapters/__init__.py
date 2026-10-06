"""Domain-specific adapters for test execution.

This module provides adapters that bridge domain-specific UI patterns with
generic test execution. The GenericAdapter provides universal support for
any domain without hardcoded knowledge.
"""

from .base_adapter import DomainAdapter
from .generic_adapter import GenericAdapter

__all__ = ["DomainAdapter", "GenericAdapter"]
