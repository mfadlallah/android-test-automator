"""Target grounding for Vendor Discovery domain."""

from typing import Dict, Set, Optional, Tuple
from .screens import get_visible_ocr_labels


# Domain-specific resource ID keywords
VENDOR_DISCOVERY_ALIASES = {
    'restaurants': {
        'restaurants', 'المطاعم', 'مطاعم',
        'restaurant', 'food', 'vendor', 'vendors', 'vertical', 'home',
        'homeRestaurantsVertical',  # Common resource ID pattern
    },
    'filters': {
        'filters', 'filter', 'التصفيات', 'filtration', 'cuisine', 'cuisines',
        'filterPill', 'filterButton',
    },
    'filters_list': {
        'cuisines', 'cuisine', 'المطابخ', 'rating', 'ratings',
        'sortOption', 'cuisineRecycler',
    },
    'restaurant_item': {
        'restaurant', 'vendor', 'item', 'card', 'row', 'element',
        'vendorItem', 'vendorCard', 'vendorRow',
    },
    'restaurant_list': {
        'restaurant', 'vendor', 'list', 'recycler', 'scroll',
        'vendorsRecycler', 'vendorsList',
    },
    'layout_toggle': {
        'layout', 'toggle', 'segment', 'view', 'card', 'row',
        'layoutToggle', 'viewToggle',
    },
    'hour_offer': {
        'hour', 'offer', 'expires', 'promotion', 'banner',
        'hourOfferSheet', 'promotionBanner', 'advertisingSheet',
    },
}


def get_resource_aliases(target: str) -> Set[str]:
    """
    Get domain-specific resource ID keywords for a target.

    Args:
        target: Semantic target name (e.g., 'Restaurants', 'Filters')

    Returns:
        Set of resource ID keywords to search for
    """
    target_lower = target.lower() if target else ''

    # Check for exact matches in aliases
    for key, aliases in VENDOR_DISCOVERY_ALIASES.items():
        if target_lower in key or key in target_lower:
            return aliases.copy()

    # Default: search for target words directly
    words = set(target_lower.split())
    found_aliases = set()

    for key, aliases in VENDOR_DISCOVERY_ALIASES.items():
        if words & aliases:
            found_aliases.update(aliases)

    return found_aliases if found_aliases else words


def ground_restaurants_list(observation: Dict) -> Optional[Tuple[int, int, int, int]]:
    """
    Find the restaurant list/recycler bounds.

    Returns:
        (x1, y1, x2, y2) bounds or None if not found
    """
    # Look for vendorsRecycler node
    for node in observation.get('nodes', []):
        resource_id = node.get('resource_id', '').lower()
        if 'vendorsRecycler' in resource_id:
            bounds = node.get('bounds', [])
            if len(bounds) == 4:
                return tuple(bounds)

    # Fallback: look for large scrollable container
    for node in observation.get('nodes', []):
        if not node.get('scrollable'):
            continue

        bounds = node.get('bounds', [0, 0, 0, 0])
        x1, y1, x2, y2 = bounds
        width = x2 - x1
        height = y2 - y1

        # Look for scrollable region sized like a list (tall, full width)
        if width > 300 and height > 400:
            resource_id = node.get('resource_id', '').lower()
            if any(kw in resource_id for kw in ['vendor', 'recycler', 'list']):
                return (x1, y1, x2, y2)

    return None


def ground_filters_pill(observation: Dict) -> Optional[Tuple[int, int, int, int]]:
    """
    Find the Filters pill/button bounds.

    Returns:
        (x1, y1, x2, y2) bounds or None if not found
    """
    # Look for "Filters" in OCR
    ocr_labels = get_visible_ocr_labels(observation, confidence_threshold=0.7)

    for row in observation.get('ocr', []):
        text = ' '.join(row.get('text', '').split()).casefold()
        if text in {'filters', 'filter', 'التصفيات'}:
            bounds = row.get('bounds', [])
            if len(bounds) == 4:
                return tuple(bounds)

    # Look for filters node in hierarchy
    for node in observation.get('nodes', []):
        resource_id = node.get('resource_id', '').lower()
        text = node.get('text', '').lower()

        if 'filter' in resource_id or text in {'filters', 'filter', 'التصفيات'}:
            bounds = node.get('bounds', [])
            if len(bounds) == 4:
                return tuple(bounds)

    return None
