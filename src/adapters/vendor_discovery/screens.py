"""Screen detection for Vendor Discovery domain."""

from typing import Dict, Any, Set


def current_restaurants_listing(observation: Dict[str, Any]) -> bool:
    """
    Detect if the current screen is the Restaurants/Vendor Discovery listing.

    Uses both accessibility hierarchy (resource IDs) and OCR as fallback.
    """
    # Check accessibility hierarchy first - most reliable
    resource_ids = {
        node.get('resource_id', '').split(':id/')[-1]
        for node in observation.get('nodes', [])
    }

    if {'vendors_title', 'vendorsRecycler'} <= resource_ids:
        return True

    # OCR fallback with confidence threshold
    ocr_labels = {
        ' '.join(row.get('text', '').split()).casefold()
        for row in observation.get('ocr', [])
        if row.get('confidence', 0) >= 0.7
    }

    # Check for title indicators (multiple languages)
    has_title = bool(ocr_labels & {'restaurants', 'المطاعم', 'مطاعم'})

    # Check for listing-specific cues
    listing_cues = {
        'filters', 'cuisines', 'top rated', 'التصفيات', 'المطابخ',
    }
    has_listing_cue = bool(ocr_labels & listing_cues) or any(
        'search for a restaurant or meal' in label for label in ocr_labels
    )

    return has_title and has_listing_cue


def current_home_screen(observation: Dict[str, Any]) -> bool:
    """
    Detect if the current screen is the Home screen.

    Used to validate recovery actions don't unintentionally navigate away.
    """
    resource_ids = {
        node.get('resource_id', '').split(':id/')[-1]
        for node in observation.get('nodes', [])
    }

    if 'welcome_message_headline' in resource_ids:
        return True

    ocr_labels = {
        ' '.join(row.get('text', '').split()).casefold()
        for row in observation.get('ocr', [])
        if row.get('confidence', 0) >= 0.7
    }

    has_welcome = any(
        'what would you like to order' in label for label in ocr_labels
    )
    has_home = bool(ocr_labels & {'home', 'الرئيسية'})
    has_vertical = bool(ocr_labels & {'restaurants', 'المطاعم', 'مطاعم'})

    return has_welcome and (has_home or has_vertical)


def get_visible_ocr_labels(observation: Dict[str, Any], confidence_threshold: float = 0.7) -> Set[str]:
    """
    Extract visible OCR labels from observation.

    Args:
        observation: Current screen state
        confidence_threshold: Minimum OCR confidence to include

    Returns:
        Set of normalized OCR text labels
    """
    return {
        ' '.join(row.get('text', '').split()).casefold()
        for row in observation.get('ocr', [])
        if row.get('confidence', 0) >= confidence_threshold
    }
