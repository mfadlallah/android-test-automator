"""Main Vendor Discovery domain adapter."""

from typing import Dict, Any, Optional, Set
from ..base_adapter import DomainAdapter, BoundingBox
from .screens import current_restaurants_listing, get_visible_ocr_labels
from .layout import locate_layout_toggle_visual, get_layout_toggle_buttons
from .grounding import get_resource_aliases, ground_restaurants_list, ground_filters_pill
from .assertions import get_assertion_crop_for_first_item


class VendorDiscoveryAdapter(DomainAdapter):
    """
    Domain adapter for Vendor Discovery (Restaurants listing) domain.

    Handles grounding, verification, and recovery for restaurant/vendor
    listing screens with layout toggles, filters, and item assertions.
    """

    @property
    def name(self) -> str:
        """Domain name."""
        return "vendor_discovery"

    def detect_screen(self, observation: Dict[str, Any]) -> bool:
        """Detect if current screen is Restaurants listing."""
        return current_restaurants_listing(observation)

    def ground_target(
        self,
        target: str,
        observation: Dict[str, Any],
        hints: Optional[list] = None
    ) -> Optional[BoundingBox]:
        """
        Ground a semantic target in Vendor Discovery domain.

        Special handling for known targets like:
        - "Restaurants" → already grounded (triggers this domain detection)
        - "Filters" → Filters pill/button
        - "restaurant list" → RecyclerView container

        For other targets, uses generic grounding via OCR/hierarchy.
        """
        target_lower = (target or '').lower()

        # Known targets with specific grounding logic
        if any(word in target_lower for word in ['filter', 'التصفيات']):
            bounds = ground_filters_pill(observation)
            if bounds:
                return BoundingBox(*bounds)

        if any(word in target_lower for word in ['restaurant', 'list', 'scroll', 'vendor']):
            bounds = ground_restaurants_list(observation)
            if bounds:
                return BoundingBox(*bounds)

        # Fallback to generic grounding for other targets
        # (OCR, accessibility hierarchy, resource IDs)
        return self._generic_ground(target, observation, hints)

    def find_scrollable_region(
        self,
        target: str,
        observation: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """
        Find the scrollable region for a target.

        For restaurant list targets, returns the vendorsRecycler bounds.
        """
        target_lower = (target or '').lower()

        if any(word in target_lower for word in ['restaurant', 'list', 'vendor', 'scroll']):
            bounds = ground_restaurants_list(observation)
            if bounds:
                return BoundingBox(*bounds)

        return None

    def get_assertion_crop(
        self,
        target: str,
        observation: Dict[str, Any],
        step: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """
        Get crop bounds for scoped assertions.

        For "first restaurant item" targets, finds and crops the first
        visible item. For contains/not_contains, finds specific labels
        and returns tight crops.
        """
        target_lower = (target or '').lower()

        # Special handling for first item assertions
        if 'first' in target_lower and any(
            word in target_lower for word in ['item', 'restaurant', 'card', 'row']
        ):
            crop = get_assertion_crop_for_first_item(observation, step)
            if crop:
                return BoundingBox(*crop)

        # For other targets, generic grounding
        bounds = self._generic_ground(target, observation)
        if bounds:
            return bounds

        return None

    def handle_recovery(
        self,
        observation: Dict[str, Any],
        history: list,
        error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Handle Vendor Discovery–specific recovery actions.

        Currently handles Hour Offer sheet dismissal. Can be extended
        for other known interruptions.
        """
        # TODO: Implement hour_offer_gate logic
        # For now, return None to fall back to generic recovery
        return None

    def get_resource_aliases(self, target: str) -> Set[str]:
        """Return Vendor Discovery resource ID aliases for target."""
        return get_resource_aliases(target)

    def validate_destination(
        self,
        observation: Dict[str, Any],
        target: str
    ) -> bool:
        """
        Validate that we reached the expected destination.

        For Restaurants target, confirm we're on the listing screen.
        """
        target_lower = (target or '').lower()

        if any(word in target_lower for word in ['restaurant', 'المطاعم']):
            return current_restaurants_listing(observation)

        return True

    # Private helper methods

    def _generic_ground(
        self,
        target: str,
        observation: Dict[str, Any],
        hints: Optional[list] = None
    ) -> Optional[BoundingBox]:
        """
        Generic grounding using OCR, hierarchy, and resource IDs.

        This is a simplified version. The real implementation would
        delegate to the core grounding module.
        """
        # Get domain-specific resource aliases
        aliases = self.get_resource_aliases(target)

        # Search OCR
        target_lower = (target or '').lower()
        ocr_labels = get_visible_ocr_labels(observation)

        for row in observation.get('ocr', []):
            row_text = ' '.join(row.get('text', '').split()).casefold()
            if row_text == target_lower or any(
                alias in row_text for alias in aliases
            ):
                bounds = row.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Search accessibility hierarchy
        for node in observation.get('nodes', []):
            node_text = node.get('text', '').lower()
            resource_id = node.get('resource_id', '').lower()

            if (node_text == target_lower or
                any(alias in resource_id for alias in aliases)):
                bounds = node.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        return None
