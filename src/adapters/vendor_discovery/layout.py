"""Layout control (card/row toggle) for Vendor Discovery."""

import struct
from typing import Dict, Any, Optional, Tuple
from .screens import current_restaurants_listing, get_visible_ocr_labels


def locate_layout_toggle_visual(
    observation: Dict[str, Any],
    side: str = 'right',
) -> Optional[Tuple[int, int]]:
    """
    Locate the position of the card/row layout toggle button.

    Layout toggle is positioned beside the "Restaurants" heading.
    - Left side (83% x): Card view
    - Right side (91% x): Row view

    Args:
        observation: Current screen state
        side: 'left' for card view or 'right' for row view

    Returns:
        (x, y) position to tap, or None if toggle not found.

    Raises:
        ValueError: If not on Restaurants listing or heading unavailable
    """
    if not current_restaurants_listing(observation):
        raise ValueError(
            'Cannot ground layout toggle: current screen is not Restaurants listing'
        )

    # Get screenshot dimensions
    png = observation.get('png', b'')
    if len(png) < 24:
        raise ValueError('Screenshot data too short to extract dimensions')

    width, height = struct.unpack('>II', png[16:24])

    # Find "Restaurants" heading via OCR
    labels = get_visible_ocr_labels(observation)

    if not labels & {'restaurants', 'المطاعم', 'مطاعم'}:
        raise ValueError('Restaurants heading is unavailable for safe toggle grounding')

    # Find all OCR rows with "Restaurants" text
    titles = [
        row for row in observation.get('ocr', [])
        if ' '.join(row.get('text', '').split()).casefold() in
           {'restaurants', 'المطاعم', 'مطاعم'}
        and row.get('confidence', 0) >= 0.7
    ]

    if not titles:
        raise ValueError('Restaurants heading OCR not found')

    # Use topmost title for Y coordinate
    title = min(titles, key=lambda row: row['bounds'][1])
    title_y1, title_y2 = title['bounds'][1], title['bounds'][3]
    y = (title_y1 + title_y2) // 2

    # X position depends on which toggle button
    x = round(width * (0.91 if side == 'right' else 0.83))

    # Validate that heading is in safe region for toggle grounding
    if not (x > title['bounds'][2] and height * 0.15 <= y < height * 0.62):
        raise ValueError('OCR heading is outside safe layout-toggle region')

    return (x, y)


def get_layout_toggle_buttons(
    observation: Dict[str, Any],
) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """
    Get both layout toggle button positions (left=card, right=row).

    Returns:
        ((left_x, left_y), (right_x, right_y)) or None if not found
    """
    try:
        left = locate_layout_toggle_visual(observation, side='left')
        right = locate_layout_toggle_visual(observation, side='right')
        return (left, right)
    except ValueError:
        return None
