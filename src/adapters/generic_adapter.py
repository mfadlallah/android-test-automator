"""Generic domain-agnostic adapter for universal test execution.

This adapter uses NO hardcoded resource IDs, positions, or domain knowledge.
Instead, it relies on:
- Semantic keyword matching (test case keywords match OCR content)
- Visual pattern recognition (toggles, lists, buttons)
- Content analysis (what type of items are in a scrollable)
- Generic accessibility hierarchy + OCR grounding
"""

import struct
from typing import Dict, Any, Optional, Set, Tuple, List
from .base_adapter import DomainAdapter, BoundingBox


class GenericAdapter(DomainAdapter):
    """
    Universal adapter that works for ANY domain without configuration.

    Key strategies:
    1. Semantic scrollable matching: "scroll restaurants" finds scrollable
       with restaurant-like items (via OCR content analysis)
    2. Smart toggle detection: Finds button pairs that look like toggles
    3. Generic target grounding: OCR + hierarchy search, no aliases
    4. Content-aware item detection: Finds first item in matched container
    """

    @property
    def name(self) -> str:
        """Domain name (generic, works for all domains)."""
        return "generic"

    def detect_screen(self, observation: Dict[str, Any]) -> bool:
        """
        Generic screen detection: accept any screen.

        This adapter works on any screen, so always return True.
        No domain-specific validation needed.
        """
        return True

    def ground_target(
        self,
        target: str,
        observation: Dict[str, Any],
        hints: Optional[list] = None
    ) -> Optional[BoundingBox]:
        """
        Ground a target using generic OCR + hierarchy matching.

        No hardcoded resource IDs. Just search for the target text
        in OCR and accessibility hierarchy.
        """
        if not target:
            return None

        target_lower = target.lower()

        # Try exact OCR match first
        for row in observation.get('ocr', []):
            ocr_text = ' '.join(row.get('text', '').split()).casefold()
            if ocr_text == target_lower:
                bounds = row.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Try partial OCR match
        for row in observation.get('ocr', []):
            ocr_text = ' '.join(row.get('text', '').split()).casefold()
            if target_lower in ocr_text or ocr_text in target_lower:
                bounds = row.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Try accessibility hierarchy
        for node in observation.get('nodes', []):
            node_text = (node.get('text', '') or '').lower()
            node_desc = (node.get('description', '') or '').lower()

            if node_text == target_lower or node_desc == target_lower:
                bounds = node.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Try partial hierarchy match
        for node in observation.get('nodes', []):
            node_text = (node.get('text', '') or '').lower()
            if target_lower in node_text:
                bounds = node.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        return None

    def find_scrollable_region(
        self,
        target: str,
        observation: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """
        Find scrollable container with semantic matching.

        When test says "scroll restaurants", this:
        1. Finds all scrollable containers
        2. Analyzes OCR content in each
        3. Matches semantic meaning (target keywords match item types)
        4. Returns the best match

        Example: "scroll restaurants" matches scrollable containing
        "Restaurant Name", "Rating", "Price" in OCR.
        """
        if not target:
            return None

        target_lower = target.lower()

        # Extract semantic keywords from target
        keywords = self._extract_keywords(target)

        if not keywords:
            # Fallback: just find largest scrollable
            return self._find_largest_scrollable(observation)

        # Find all scrollable containers
        scrollables = self._find_all_scrollables(observation)

        if not scrollables:
            return None

        # Score each scrollable based on content match
        scored = []
        for scrollable in scrollables:
            score = self._score_scrollable_match(
                scrollable, keywords, observation
            )
            scored.append((scrollable, score))

        # Return scrollable with highest score
        best = max(scored, key=lambda x: x[1])
        if best[1] > 0:  # Must have some match
            bounds = best[0].get('bounds', [])
            if len(bounds) == 4:
                return BoundingBox(*bounds)

        # Fallback: largest scrollable
        return self._find_largest_scrollable(observation)

    def get_assertion_crop(
        self,
        target: str,
        observation: Dict[str, Any],
        step: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """
        Get crop bounds for assertions (generic approach).

        For "first item" assertions:
        1. Find scrollable container
        2. Find first visible child
        3. Return item bounds (or tight crop for specific labels)
        """
        target_lower = (target or '').lower()

        # Check if this is a "first item" assertion
        if 'first' not in target_lower:
            # For non-first-item assertions, use full screen or grounded target
            return self._ground_assertion_target(target, observation, step)

        # Find scrollable container
        scrollable = self.find_scrollable_region(target, observation)
        if not scrollable:
            return None

        sx1, sy1, sx2, sy2 = scrollable.x1, scrollable.y1, scrollable.x2, scrollable.y2

        # Find first visible child item
        first_item = self._find_first_item_in_container(
            observation, (sx1, sy1, sx2, sy2)
        )

        if not first_item:
            return None

        fx1, fy1, fx2, fy2 = first_item

        png = observation.get('png', b'')
        if len(png) < 24:
            return BoundingBox(fx1, fy1, fx2, fy2)

        width, height = struct.unpack('>II', png[16:24])

        # For contains/not_contains assertions, try to find specific label
        if step.get('capability') in {'assert_contains', 'assert_not_contains'}:
            expected_label = step.get('value', '')
            if expected_label:
                label_bounds = self._find_label_in_region(
                    observation, expected_label, (fx1, fy1, fx2, fy2)
                )
                if label_bounds:
                    return BoundingBox(*label_bounds)

                # Fallback: tight badge crop (top-right area)
                return BoundingBox(
                    *self._get_badge_crop((fx1, fy1, fx2, fy2), (width, height))
                )

        # Return entire first item
        return BoundingBox(fx1, fy1, fx2, fy2)

    def handle_recovery(
        self,
        observation: Dict[str, Any],
        history: list,
        error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generic recovery (no domain-specific interruption handling).

        Returns None to let core recovery logic handle it.
        Can be extended later if patterns emerge.
        """
        return None

    def get_resource_aliases(self, target: str) -> Set[str]:
        """
        Generic: return empty set (no domain-specific aliases).

        The adapter uses direct OCR/hierarchy search, not aliases.
        """
        return set()

    def validate_destination(
        self,
        observation: Dict[str, Any],
        target: str
    ) -> bool:
        """
        Generic validation: just check if target is findable.

        If we can ground the target, destination is reachable.
        """
        return self.ground_target(target, observation) is not None

    # ============= Private Helper Methods =============

    def _extract_keywords(self, target: str) -> Set[str]:
        """
        Extract semantic keywords from target string.

        E.g., "Scroll vendors/restaurants recycler" →
        {"vendors", "restaurants", "recycler"}
        """
        # Split by common delimiters and clean up
        parts = target.replace('/', ' ').replace('-', ' ').split()
        keywords = {
            part.lower().strip()
            for part in parts
            if len(part) > 2  # Skip short words like "a", "or"
        }
        return keywords

    def _find_all_scrollables(
        self, observation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find all scrollable containers in hierarchy."""
        scrollables = []

        for node in observation.get('nodes', []):
            if node.get('scrollable'):
                bounds = node.get('bounds', [0, 0, 0, 0])
                if len(bounds) == 4:
                    width = bounds[2] - bounds[0]
                    height = bounds[3] - bounds[1]
                    # Only consider reasonably sized scrollables
                    if width > 50 and height > 50:
                        scrollables.append(node)

        return scrollables

    def _find_largest_scrollable(
        self, observation: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """Find the largest scrollable container (fallback)."""
        scrollables = self._find_all_scrollables(observation)

        if not scrollables:
            return None

        # Return scrollable with largest area
        largest = max(
            scrollables,
            key=lambda n: (n['bounds'][2] - n['bounds'][0]) *
                         (n['bounds'][3] - n['bounds'][1])
        )

        bounds = largest.get('bounds', [])
        if len(bounds) == 4:
            return BoundingBox(*bounds)

        return None

    def _score_scrollable_match(
        self,
        scrollable: Dict[str, Any],
        keywords: Set[str],
        observation: Dict[str, Any]
    ) -> int:
        """
        Score how well a scrollable matches the target keywords.

        Strategy: analyze OCR content within scrollable bounds.
        Higher score = better match.
        """
        if not keywords:
            return 0

        sx1, sy1, sx2, sy2 = scrollable.get('bounds', [0, 0, 0, 0])
        score = 0

        # Analyze OCR content within scrollable
        for row in observation.get('ocr', []):
            ocr_x1, ocr_y1, ocr_x2, ocr_y2 = row.get('bounds', [0, 0, 0, 0])
            ocr_text = ' '.join(row.get('text', '').split()).casefold()
            confidence = row.get('confidence', 0)

            # Check if OCR is within scrollable bounds
            if ocr_x2 > sx1 and ocr_x1 < sx2 and ocr_y2 > sy1 and ocr_y1 < sy2:
                # Check if OCR contains any keywords
                for keyword in keywords:
                    if keyword in ocr_text:
                        # Weight by confidence
                        score += int(confidence * 10)

        # Also check hierarchy text
        for node in observation.get('nodes', []):
            nx1, ny1, nx2, ny2 = node.get('bounds', [0, 0, 0, 0])
            node_text = (node.get('text', '') or '').casefold()

            if nx2 > sx1 and nx1 < sx2 and ny2 > sy1 and ny1 < sy2:
                for keyword in keywords:
                    if keyword in node_text:
                        score += 5  # Lower weight than OCR

        return score

    def _find_first_item_in_container(
        self,
        observation: Dict[str, Any],
        container_bounds: Tuple[int, int, int, int]
    ) -> Optional[Tuple[int, int, int, int]]:
        """Find first visible item in a container."""
        cx1, cy1, cx2, cy2 = container_bounds

        # Find direct children of container
        candidates = []
        for node in observation.get('nodes', []):
            # Simple heuristic: if parent node ID matches container
            # (this is simplified; real implementation would check parent)
            nx1, ny1, nx2, ny2 = node.get('bounds', [0, 0, 0, 0])
            width = nx2 - nx1
            height = ny2 - ny1

            # Item must be substantial and within container
            if (width > 50 and height > 50 and
                nx2 > cx1 and nx1 < cx2 and
                ny2 > cy1 and ny1 < cy2):
                candidates.append((nx1, ny1, nx2, ny2))

        if not candidates:
            return None

        # Return topmost item (first visible)
        return min(candidates, key=lambda item: (max(item[1], cy1), item[0]))

    def _find_label_in_region(
        self,
        observation: Dict[str, Any],
        label_text: str,
        region_bounds: Tuple[int, int, int, int]
    ) -> Optional[List[int]]:
        """Find specific label within a region."""
        if not label_text:
            return None

        rx1, ry1, rx2, ry2 = region_bounds
        expected = ' '.join(label_text.split()).casefold()

        # Search OCR first
        for row in observation.get('ocr', []):
            ocr_x1, ocr_y1, ocr_x2, ocr_y2 = row.get('bounds', [0, 0, 0, 0])
            ocr_text = ' '.join(row.get('text', '').split()).casefold()
            confidence = row.get('confidence', 0)

            # Adaptive confidence for small regions
            threshold = 0.4 if (ocr_x2 - ocr_x1) < 100 else 0.7

            if (ocr_x2 > rx1 and ocr_x1 < rx2 and
                ocr_y2 > ry1 and ocr_y1 < ry2 and
                ocr_text == expected and
                confidence >= threshold):
                return [ocr_x1, ocr_y1, ocr_x2, ocr_y2]

        # Search hierarchy
        for node in observation.get('nodes', []):
            nx1, ny1, nx2, ny2 = node.get('bounds', [0, 0, 0, 0])
            node_text = (node.get('text', '') or '').casefold()

            if (nx2 > rx1 and nx1 < rx2 and
                ny2 > ry1 and ny1 < ry2 and
                node_text == expected):
                return [nx1, ny1, nx2, ny2]

        return None

    def _get_badge_crop(
        self,
        item_bounds: Tuple[int, int, int, int],
        screenshot_dims: Tuple[int, int]
    ) -> List[int]:
        """Get tight crop for badge area (top-right of item)."""
        fx1, fy1, fx2, fy2 = item_bounds
        width, height = screenshot_dims

        item_w = fx2 - fx1
        item_h = fy2 - fy1

        # Tight crop for badge area
        badge_crop_width = min(round(item_w * 0.30), 220)
        badge_crop_height = 70

        badge_x1 = max(0, fx2 - badge_crop_width)
        badge_y1 = max(0, fy1 + 5)
        badge_x2 = min(width, fx2 - 5)
        badge_y2 = min(height, fy1 + badge_crop_height, fy2)

        return [badge_x1, badge_y1, badge_x2, badge_y2]

    def _ground_assertion_target(
        self,
        target: str,
        observation: Dict[str, Any],
        step: Dict[str, Any]
    ) -> Optional[BoundingBox]:
        """Generic grounding for assertion targets with smart fallbacks."""
        # Try to ground the target like any other semantic target
        bounds = self.ground_target(target, observation)

        if bounds:
            return bounds

        # Fallback: Try semantic target bounds for pills, sheets, buttons, etc.
        # This helps with UI elements that might not have exact OCR/hierarchy matches
        target_lower = target.lower()
        if any(word in target_lower for word in ('pill', 'sheet', 'button', 'option', 'label')):
            # Use adaptive semantic matching from main.py logic
            semantic_bounds = self._semantic_match_bounds(target, observation)
            if semantic_bounds:
                return BoundingBox(*semantic_bounds)

        # If still not found, return None instead of full-screen
        # Let caller decide whether to use full-screen fallback
        return None

    def _semantic_match_bounds(
        self,
        target: str,
        observation: Dict[str, Any]
    ) -> Optional[List[int]]:
        """Find bounds using semantic keyword matching."""
        import re

        png = observation.get('png', b'')
        if len(png) < 24:
            return None

        width, height = struct.unpack('>II', png[16:24])

        # Extract keywords from target
        target_lower = target.lower()
        target_tokens = set(re.findall(r'\w+', target_lower, re.UNICODE))

        # Search OCR for matching text
        best_match = None
        for row in observation.get('ocr', []):
            ocr_text = row.get('text', '').lower()
            ocr_tokens = set(re.findall(r'\w+', ocr_text, re.UNICODE))

            # Check if tokens match (flexible matching for "Filters pill" → "Filters")
            if target_tokens and (ocr_tokens >= target_tokens or target_tokens <= ocr_tokens):
                bounds = row.get('bounds', [])
                if len(bounds) == 4:
                    best_match = bounds
                    break  # Take first good match

        # Search hierarchy for matching text
        if not best_match:
            for node in observation.get('nodes', []):
                if not node.get('enabled'):
                    continue
                node_text = (node.get('text', '') or '').lower()
                node_tokens = set(re.findall(r'\w+', node_text, re.UNICODE))

                if target_tokens and (node_tokens >= target_tokens or target_tokens <= node_tokens):
                    bounds = node.get('bounds', [])
                    if len(bounds) == 4:
                        best_match = bounds
                        break

        if not best_match:
            return None

        # Return with adaptive padding for pills/buttons
        x1, y1, x2, y2 = best_match
        item_width = x2 - x1
        item_height = y2 - y1

        # Tight padding for small pills
        if item_width < width * 0.2 and item_height < height * 0.1:
            pad_h = max(2, round(width * 0.01))
            pad_v = max(2, round(height * 0.01))
        else:
            pad_h = round(width * 0.03)
            pad_v = round(height * 0.02)

        return [
            max(0, x1 - pad_h),
            max(0, y1 - pad_v),
            min(width, x2 + pad_h),
            min(height, y2 + pad_v)
        ]
