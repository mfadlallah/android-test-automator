"""Assertion crop logic for Vendor Discovery domain."""

import struct
from typing import Dict, Any, Optional, List, Tuple


def find_first_restaurant_item(
    observation: Dict[str, Any],
    container_bounds: Tuple[int, int, int, int]
) -> Optional[Dict[str, Any]]:
    """
    Find the first visible restaurant item in the listing.

    Args:
        observation: Current screen state
        container_bounds: (x1, y1, x2, y2) of the restaurant list container

    Returns:
        Node dict for first item or None
    """
    x1, y1, x2, y2 = container_bounds
    png = observation.get('png', b'')

    if len(png) < 24:
        return None

    width, height = struct.unpack('>II', png[16:24])

    # Find direct children of container (restaurant items)
    candidates = []
    for node in observation.get('nodes', []):
        if node.get('parent') != container_bounds:
            continue

        node_x1, node_y1, node_x2, node_y2 = node.get('bounds', [0, 0, 0, 0])
        node_width = node_x2 - node_x1
        node_height = node_y2 - node_y1

        # Item must be substantial size and overlap container
        if (node_width >= width * 0.65 and node_height >= height * 0.08 and
            node_y2 > y1 and node_y1 < y2):
            candidates.append(node)

    if not candidates:
        return None

    # Prefer fully visible items
    fully_visible = [
        n for n in candidates
        if n['bounds'][1] >= y1 and n['bounds'][3] <= y2
    ]

    if fully_visible:
        return min(fully_visible, key=lambda n: n['bounds'][0])

    # Fallback to topmost item
    return min(candidates, key=lambda n: (max(n['bounds'][1], y1), n['bounds'][0]))


def find_label_in_item(
    observation: Dict[str, Any],
    label_text: str,
    item_bounds: Tuple[int, int, int, int]
) -> Optional[List[int]]:
    """
    Find a specific label within a restaurant item.

    Searches OCR and accessibility hierarchy for exact label match.

    Args:
        observation: Current screen state
        label_text: Text to search for (e.g., "Ad", "Promoted")
        item_bounds: (x1, y1, x2, y2) of the item to search within

    Returns:
        [x1, y1, x2, y2] bounds of label or None if not found
    """
    fx1, fy1, fx2, fy2 = item_bounds
    expected = ' '.join(str(label_text).split()).casefold()

    if not expected:
        return None

    # Search OCR first (faster, more reliable for badges)
    for row in observation.get('ocr', []):
        ocr_x1, ocr_y1, ocr_x2, ocr_y2 = row.get('bounds', [0, 0, 0, 0])
        ocr_text = ' '.join(row.get('text', '').split()).casefold()
        ocr_confidence = row.get('confidence', 0.0)

        # Adaptive confidence for small badges (lower threshold)
        threshold = 0.4 if (ocr_x2 - ocr_x1) < 100 else 0.7

        # Check if within item bounds and matches
        if (ocr_x2 > fx1 and ocr_x1 < fx2 and
            ocr_y2 > fy1 and ocr_y1 < fy2 and
            ocr_text == expected and
            ocr_confidence >= threshold):
            return [ocr_x1, ocr_y1, ocr_x2, ocr_y2]

    # Search accessibility hierarchy
    for node in observation.get('nodes', []):
        node_x1, node_y1, node_x2, node_y2 = node.get('bounds', [0, 0, 0, 0])
        node_text = node.get('text', '')
        node_label = ' '.join(str(node_text).split()).casefold()

        # Check if within item bounds and matches
        if (node_x2 > fx1 and node_x1 < fx2 and
            node_y2 > fy1 and node_y1 < fy2 and
            node_label == expected):
            return [node_x1, node_y1, node_x2, node_y2]

    return None


def get_badge_crop_bounds(
    item_bounds: Tuple[int, int, int, int],
    screenshot_dims: Tuple[int, int]
) -> List[int]:
    """
    Get tight crop bounds for badge area (top-right of item).

    Used as fallback when label not found via OCR/accessibility.

    Args:
        item_bounds: (x1, y1, x2, y2) of the restaurant item
        screenshot_dims: (width, height) of screenshot

    Returns:
        [x1, y1, x2, y2] crop bounds
    """
    fx1, fy1, fx2, fy2 = item_bounds
    width, height = screenshot_dims

    item_w = fx2 - fx1
    item_h = fy2 - fy1

    # Tight crop for badge area only (top-right of first item)
    badge_crop_width = min(round(item_w * 0.30), 220)
    badge_crop_height = 70  # Fixed height to avoid second item

    badge_x1 = max(0, fx2 - badge_crop_width)
    badge_y1 = max(0, fy1 + 5)  # Small offset from top
    badge_x2 = min(width, fx2 - 5)  # Small margin from edge
    badge_y2 = min(height, fy1 + badge_crop_height)

    # Safety: ensure crop doesn't exceed first item bounds
    badge_y2 = min(badge_y2, fy2)

    return [badge_x1, badge_y1, badge_x2, badge_y2]


def get_assertion_crop_for_first_item(
    observation: Dict[str, Any],
    step: Dict[str, Any]
) -> Optional[List[int]]:
    """
    Get crop bounds for assertion on first restaurant item.

    Handles contains/not_contains assertions by:
    1. Finding the first visible restaurant item
    2. For specific labels, cropping tightly around the label
    3. Falling back to badge area crop if label not found

    Args:
        observation: Current screen state
        step: Assertion step from plan

    Returns:
        [x1, y1, x2, y2] crop bounds or None
    """
    png = observation.get('png', b'')
    if len(png) < 24:
        return None

    width, height = struct.unpack('>II', png[16:24])

    # Find restaurant list container
    candidates = []
    for node in observation.get('nodes', []):
        resource_id = node.get('resource_id', '').casefold()
        x1, y1, x2, y2 = node.get('bounds', [0, 0, 0, 0])
        node_width = x2 - x1
        node_height = y2 - y1

        # Look for large scrollable container (likely restaurant list)
        if (node_width >= width * 0.65 and node_height >= height * 0.25 and
            (node.get('scrollable') or
             'recycler' in resource_id or
             ('vendor' in resource_id and 'list' in resource_id))):
            candidates.append(node)

    if not candidates:
        return None

    # Use largest container (likely the main list)
    container = max(
        candidates,
        key=lambda n: (n['bounds'][2] - n['bounds'][0]) *
                     (n['bounds'][3] - n['bounds'][1])
    )

    container_bounds = tuple(container['bounds'])

    # Find first item
    first_item = find_first_restaurant_item(observation, container_bounds)
    if not first_item:
        return None

    fx1, fy1, fx2, fy2 = first_item['bounds']

    # For contains/not_contains, try to find specific label
    if step.get('capability') in {'assert_contains', 'assert_not_contains'}:
        expected_label = step.get('value', '')

        if expected_label:
            label_bounds = find_label_in_item(
                observation, expected_label, (fx1, fy1, fx2, fy2)
            )

            if label_bounds:
                # Found label - return tight crop around it
                lx1, ly1, lx2, ly2 = label_bounds

                # Add small padding around label
                padding = 10
                return [
                    max(0, lx1 - padding),
                    max(0, ly1 - padding),
                    min(width, lx2 + padding),
                    min(height, ly2 + padding)
                ]

            # Label not found - use badge crop fallback
            return get_badge_crop_bounds((fx1, fy1, fx2, fy2), (width, height))

    # For other assertions, return entire first item (constrained to container)
    cx1, cy1, cx2, cy2 = container_bounds
    return [
        max(0, fx1, cx1),
        max(0, fy1, cy1),
        min(width, fx2, cx2),
        min(height, fy2, cy2)
    ]
