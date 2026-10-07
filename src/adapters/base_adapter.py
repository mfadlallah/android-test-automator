"""Abstract base class for domain-specific adapters."""

from abc import ABC, abstractmethod
from typing import Optional, Set, Tuple, Dict, Any


class BoundingBox:
    """Represents a rectangular region on screen."""

    def __init__(self, x1: int, y1: int, x2: int, y2: int):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def to_tuple(self) -> Tuple[int, int, int, int]:
        """Return as (x1, y1, x2, y2)."""
        return (self.x1, self.y1, self.x2, self.y2)


class DomainAdapter(ABC):
    """
    Abstract base class for domain-specific adapters.

    Each domain (Vendor Discovery, Order Management, Checkout, etc.) implements
    an adapter that provides grounding, verification, and recovery logic specific
    to that domain's UI patterns.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Domain name (e.g., 'vendor_discovery', 'order_management')."""
        pass

    @abstractmethod
    def detect_screen(self, observation: Dict[str, Any]) -> bool:
        """
        Detect whether the current observation is in this domain's main screen.

        Args:
            observation: Current screen state with 'nodes', 'ocr', 'screenshot', etc.

        Returns:
            True if this is a screen belonging to this domain, False otherwise.
        """
        pass

    @abstractmethod
    def ground_target(
        self,
        target: str,
        observation: Dict[str, Any],
        hints: Optional[list] = None
    ) -> Optional[BoundingBox]:
        """
        Locate a semantic target on screen using domain knowledge.

        Uses accessibility hierarchy, resource IDs, OCR, and domain-specific
        heuristics to find the target element.

        Args:
            target: Semantic target name (e.g., 'Restaurants', 'Filters')
            observation: Current screen state
            hints: Optional resource ID keywords from the plan

        Returns:
            BoundingBox if target found, None if not found or ambiguous.
        """
        pass

    @abstractmethod
    def find_scrollable_region(
        self,
        target: str,
        observation: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """
        Identify the scrollable container for a given target.

        Args:
            target: Target name (e.g., 'restaurant list', 'meals list')
            observation: Current screen state

        Returns:
            BoundingBox of scrollable region or None if not found.
        """
        pass

    @abstractmethod
    def get_assertion_crop(
        self,
        target: str,
        observation: Dict[str, Any],
        step: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """
        Determine crop bounds for scoped visual assertions.

        For assertions on specific items/regions (e.g., "first restaurant item",
        "Ad badge"), returns a tight crop focused on that region.

        Args:
            target: Assertion target (e.g., 'first restaurant item', 'Ad badge')
            observation: Current screen state
            step: Plan step containing assertion details

        Returns:
            BoundingBox for crop or None if cannot determine.
        """
        pass

    @abstractmethod
    def handle_recovery(
        self,
        observation: Dict[str, Any],
        history: list,
        error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest a domain-specific recovery action for known interruptions.

        Handles sheets, dialogs, and other expected interruptions specific
        to this domain (e.g., Hour Offer sheet for Vendor Discovery).

        Args:
            observation: Current screen state
            history: List of previous steps/actions
            error: Optional error message that triggered recovery

        Returns:
            Recovery action dict (action, target, reason) or None if no recovery.
        """
        pass

    def get_resource_aliases(self, target: str) -> Set[str]:
        """
        Return domain-specific resource ID keywords for a target.

        Override to provide domain-specific resource ID aliases that help
        with target grounding.

        Args:
            target: Target name

        Returns:
            Set of resource ID keywords to search for.
        """
        return set()

    def validate_destination(
        self,
        observation: Dict[str, Any],
        target: str
    ) -> bool:
        """
        Validate that a tap/action successfully reached the expected destination.

        Override to provide domain-specific destination validation beyond the
        generic hierarchy/OCR checks.

        Args:
            observation: Current screen state after action
            target: Expected destination target

        Returns:
            True if destination appears correct, False otherwise.
        """
        return True
