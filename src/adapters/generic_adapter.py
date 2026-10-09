"""Generic domain-agnostic adapter for universal test execution.

This adapter uses NO hardcoded resource IDs, positions, or domain knowledge.
Instead, it relies on:
- Semantic keyword matching (test case keywords match OCR content)
- Visual pattern recognition (toggles, lists, buttons)
- Content analysis (what type of items are in a scrollable)
- Generic accessibility hierarchy + OCR grounding
"""

import io
import re
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

        target_lower = self._normalize_text(target)
        target_tokens = self._semantic_tokens(target)

        # Try exact OCR match first
        for row in observation.get('ocr', []):
            ocr_text = ' '.join(row.get('text', '').split()).casefold()
            if ocr_text == target_lower:
                bounds = row.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Try token-aware OCR match.  Never use reverse substring matching:
        # a one-character status label such as "M" must not ground
        # "first restaurant item" merely because that letter occurs in it.
        for row in observation.get('ocr', []):
            ocr_text = self._normalize_text(row.get('text',''))
            ocr_tokens = self._semantic_tokens(ocr_text)
            if self._tokens_match(target_tokens,ocr_tokens):
                bounds = row.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Try accessibility hierarchy
        for node in observation.get('nodes', []):
            node_text = self._normalize_text(node.get('text',''))
            node_desc = self._normalize_text(node.get('description',''))

            if node_text == target_lower or node_desc == target_lower:
                bounds = node.get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Try token-aware hierarchy match.
        for node in observation.get('nodes', []):
            node_tokens = self._semantic_tokens(
                str(node.get('text',''))+' '+str(node.get('description','')))
            if self._tokens_match(target_tokens,node_tokens):
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
        4. Returns the best match with fallback to largest

        Example: "scroll restaurants" or "first restaurant item" matches
        scrollable containing restaurant-like items.
        """
        if not target:
            return None

        target_lower = target.lower()

        # Find all scrollable containers
        scrollables = self._find_all_scrollables(observation)

        # If NO scrollables found by scrollable flag, try to find large containers
        # that act like lists (RecyclerView, ListView, etc. may not be marked scrollable)
        if not scrollables:
            scrollables = self._find_large_containers(observation)

        if not scrollables:
            return None

        # Extract semantic keywords from target
        keywords = self._extract_keywords(target)

        # If we have keywords, try to find best match
        if keywords:
            scored = []
            for scrollable in scrollables:
                score = self._score_scrollable_match(
                    scrollable, keywords, observation
                )
                scored.append((scrollable, score))

            # Return scrollable with highest score (threshold 0 = any match)
            best = max(scored, key=lambda x: x[1])
            if best[1] > 0:
                bounds = best[0].get('bounds', [])
                if len(bounds) == 4:
                    return BoundingBox(*bounds)

        # Fallback: return largest scrollable (usually the main list)
        # This handles cases like "first restaurant item" where semantic matching
        # might not find a direct keyword match
        largest = self._find_largest_scrollable(observation)
        if largest:
            return largest

        return None

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

        # Collection phrases are structural intent, not literal labels.  For
        # example, "refreshed restaurant items" must resolve to the list
        # viewport, never to a search field that happens to contain the word
        # "restaurant".
        if 'first' not in target_lower and self._is_collection_target(target):
            collection = self.find_scrollable_region(target, observation)
            if collection:
                png = observation.get('png', b'')
                screen_dims=(None,None)
                if len(png) >= 24:
                    screen_dims=struct.unpack('>II',png[16:24])
                width,height=screen_dims
                near_full_screen=(
                    width and height and
                    (collection.x2-collection.x1)*(collection.y2-collection.y1)
                    >= width*height*.85)
                if not near_full_screen:
                    print(
                        'DEBUG adapter.get_assertion_crop: '
                        f'Using collection bounds for "{target}": '
                        f'({collection.x1}, {collection.y1}, '
                        f'{collection.x2}, {collection.y2})',
                        flush=True,
                    )
                    return collection
                print(
                    'DEBUG adapter.get_assertion_crop: ignored near-full-screen '
                    f'collection candidate for "{target}"',flush=True)

            png = observation.get('png', b'')
            if len(png) >= 24:
                width, height = struct.unpack('>II', png[16:24])
                estimated = self._estimate_first_item_from_ocr(
                    target, observation, (width, height))
                if estimated:
                    print(
                        'DEBUG adapter.get_assertion_crop: '
                        f'Using OCR collection bounds for "{target}": '
                        f'{estimated}',
                        flush=True,
                    )
                    return BoundingBox(*estimated)
            return None

        # Check if this is a "first item" assertion
        if 'first' not in target_lower:
            # For non-first-item assertions, use full screen or grounded target
            return self._ground_assertion_target(target, observation, step)

        # Find scrollable container
        scrollable = self.find_scrollable_region(target, observation)
        if not scrollable:
            print(f'DEBUG adapter.get_assertion_crop: No scrollable found for "{target}", using semantic fallback', flush=True)
            # A phrase such as "first product item" is structural intent, not
            # a literal visible label.  Estimate the first content row from
            # OCR layout instead of matching arbitrary substrings on screen.
            png = observation.get('png', b'')
            if len(png) >= 24:
                width, height = struct.unpack('>II', png[16:24])
                estimated=self._estimate_first_item_from_ocr(
                    target,observation,(width,height))
                if estimated:
                    region=tuple(estimated)
                    label=self._find_label_in_region(
                        observation,step.get('value',''),region)
                    if label and step.get('capability') in {
                            'assert_contains','assert_not_contains'}:
                        return BoundingBox(*self._expand_label_bounds(
                            label,region,(width,height)))
                    return BoundingBox(*region)
            return None

        sx1, sy1, sx2, sy2 = scrollable.x1, scrollable.y1, scrollable.x2, scrollable.y2
        print(f'DEBUG adapter.get_assertion_crop: Found scrollable for "{target}": ({sx1}, {sy1}, {sx2}, {sy2})', flush=True)

        # Find first visible child item
        first_item = self._find_first_item_in_container(
            observation, (sx1, sy1, sx2, sy2)
        )

        if not first_item:
            # Fallback: estimate first item position based on scrollable height
            # Common pattern: first item is at top of scrollable, ~80-120px tall
            item_height = min(120, int((sy2 - sy1) * 0.15))  # ~15% of scrollable or max 120px
            first_item = (sx1, sy1, sx2, sy1 + item_height)
            print(f'DEBUG adapter.get_assertion_crop: Using estimated first item for "{target}": {first_item}', flush=True)
        else:
            print(f'DEBUG adapter.get_assertion_crop: Found first item for "{target}": {first_item}', flush=True)

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
                    return BoundingBox(*self._expand_label_bounds(
                        label_bounds,(fx1,fy1,fx2,fy2),(width,height)))

                # If label not found, return full item bounds so model can assess
                # whether the expected value is present or absent in the item.
                # A tiny badge crop is insufficient for this assessment.

        # Return entire first item (for both regular assertions and when label not found)
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

    _STRUCTURAL_WORDS={
        'first','item','items','card','cards','row','rows','result','results',
        'list','container','section','visible','refreshed','vertical','horizontal',
        'the','a','an','of','in','on','with','screen','view',
    }

    def _normalize_text(self,value: str) -> str:
        return ' '.join(str(value or '').split()).casefold()

    def _semantic_tokens(self,value: str) -> Set[str]:
        normalized=re.sub(r'[^\w]+',' ',self._normalize_text(value),
                          flags=re.UNICODE)
        return {
            token for token in normalized.split()
            if len(token)>=2 and token not in self._STRUCTURAL_WORDS
        }

    def _tokens_match(self,expected: Set[str],observed: Set[str]) -> bool:
        if not expected or not observed:
            return False
        return expected <= observed or (
            len(expected)==1 and len(observed)==1 and
            next(iter(expected)).rstrip('s')==next(iter(observed)).rstrip('s')
        )

    def _is_collection_target(self, target: str) -> bool:
        """Return whether a test target describes a collection structure."""
        words=set(re.findall(r'[\w]+',self._normalize_text(target),re.UNICODE))
        return bool(words & {
            'item','items','list','lists','result','results','collection',
            'feed','rows','cards','recyclerview','listview',
        })

    def _estimate_first_item_from_ocr(
        self,
        target: str,
        observation: Dict[str,Any],
        screenshot_dims: Tuple[int,int]
    ) -> Optional[List[int]]:
        """Estimate the first list item from generic OCR layout evidence.

        The last dense horizontal OCR band below a semantic heading is treated
        as the controls row.  The first content item begins below that band.
        This is used only while accessibility hierarchy is unavailable.
        """
        width,height=screenshot_dims
        rows=[]
        for row in observation.get('ocr',[]):
            bounds=row.get('bounds',[])
            if (not isinstance(bounds,(list,tuple)) or len(bounds)!=4
                    or row.get('confidence',0)<.55):
                continue
            x1,y1,x2,y2=bounds
            if x2<=x1 or y2<=y1 or y2<height*.12 or y1>height*.72:
                continue
            rows.append(row)
        if not rows:
            return None

        target_tokens=self._semantic_tokens(target)
        anchors=[]
        for row in rows:
            observed=self._semantic_tokens(row.get('text',''))
            if self._tokens_match(target_tokens,observed):
                anchors.append(row)
        anchor_bottom=max(
            (row['bounds'][3] for row in anchors),default=round(height*.25))

        # Group OCR rows into horizontal bands.  Multiple labels on the same
        # band usually describe tabs, chips, filters, or other list controls.
        bands=[]
        for row in sorted(rows,key=lambda item:(
                (item['bounds'][1]+item['bounds'][3])//2,item['bounds'][0])):
            center=(row['bounds'][1]+row['bounds'][3])//2
            for band in bands:
                if abs(center-band['center'])<=max(36,height*.018):
                    band['rows'].append(row)
                    centers=[(item['bounds'][1]+item['bounds'][3])//2
                             for item in band['rows']]
                    band['center']=sum(centers)//len(centers)
                    break
            else:
                bands.append({'center':center,'rows':[row]})

        control_bottom=anchor_bottom
        for band in bands:
            band_bottom=max(row['bounds'][3] for row in band['rows'])
            if (len(band['rows'])>=2 and band_bottom>anchor_bottom
                    and band_bottom<=height*.58):
                control_bottom=band_bottom
                break

        # A grounded controls/heading band, rather than a fixed screen fraction,
        # supports compact rows and large image cards at different positions.
        if not anchors and control_bottom==anchor_bottom:
            return None
        start=control_bottom+max(4,round(height*.015))
        content=[row for row in observation.get('ocr',[])
                 if row.get('confidence',0)>=.55
                 and len(row.get('bounds',[]))==4
                 and row['bounds'][1]>=start
                 and row['bounds'][3]<height*.94]
        content.sort(key=lambda row:(row['bounds'][1],row['bounds'][0]))
        titles=[row for row in content
                if re.match(r'[^\W\d_]',row.get('text',''),re.UNICODE)
                and row['bounds'][0]<width*.5]
        first=titles[0] if titles else None
        next_title=None
        if first:
            fx,fy,_,fb=first['bounds']; font=fb-fy
            next_title=next((row for row in titles[1:]
                if abs(row['bounds'][0]-fx)<width*.10
                and .7*font<=row['bounds'][3]-row['bounds'][1]<=1.25*font
                and row['bounds'][1]-fb>font*2.5),None)
        limit=next_title['bounds'][1] if next_title else round(height*.94)
        previous_rows=[row for row in content if row['bounds'][1]<limit]
        trailing=max((row['bounds'][3] for row in previous_rows),default=start)
        boundary=self._ocr_item_separator(observation,start,trailing,limit)
        confirmed=first is not None and boundary is not None
        if boundary is None:
            # Keep a bounded diagnostic crop; guessed extents cannot authorize
            # first-item label verdicts.
            boundary=min(limit,start+round(height*.32))
        observation['ocr_item_scope']={
            'target':target,'bounds':[0,start,width,boundary],
            'boundary_confirmed':confirmed,
            'source':'ocr_layout_and_separator' if confirmed else 'ocr_layout_estimate',
        }
        if boundary-start<30:
            return None
        return [0,start,width,boundary]

    def _ocr_item_separator(self, observation, start, trailing, limit):
        """Locate a background gap after OCR content, independent of colors.

        Compare the row interior with its own screen gutters. Internal blank
        lines before metadata are excluded by starting after trailing OCR text.
        Pillow is optional; an unavailable separator is uncertainty.
        """
        try:
            from PIL import Image
            image=Image.open(io.BytesIO(observation.get('png',b''))).convert('RGB')
            w,h=image.size
            # Sampling caps work at ~100 pixels per row; no model call needed.
            image=image.resize((100,h))
            run=0; run_start=None
            for y in range(max(start,trailing+2),min(h,limit)):
                left=image.getpixel((1,y)); right=image.getpixel((98,y))
                background=tuple((a+b)/2 for a,b in zip(left,right))
                uniform=sum(max(abs(c-b) for c,b in zip(
                    image.getpixel((x,y)),background))<=5
                    for x in range(4,96))>=90
                if uniform:
                    if not run: run_start=y
                    run+=1
                    if run>=max(6,round(h*.004)):
                        return run_start
                else:
                    run=0
        except (ImportError,OSError,ValueError):
            return None
        return None

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
        """Find all scrollable containers in hierarchy using ADB metadata."""
        scrollables = []

        for node in observation.get('nodes', []):
            # Check scrollable flag OR resource ID/class name indicating list containers
            resource_id = node.get('resource_id', '').lower()
            node_class = (node.get('class_name') or
                          node.get('class','')).lower()

            is_scrollable = node.get('scrollable', False)
            is_list_container = (
                'recycler' in resource_id or 'recycler' in node_class or
                'listview' in resource_id or 'listview' in node_class or
                'scrollview' in resource_id or 'scrollview' in node_class or
                'viewpager' in resource_id or 'viewpager' in node_class
            )

            if is_scrollable or is_list_container:
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

    def _find_large_containers(
        self, observation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find large containers that might act like lists (even if not marked scrollable)."""
        containers = []

        for node in observation.get('nodes', []):
            bounds = node.get('bounds', [0, 0, 0, 0])
            if len(bounds) == 4:
                width = bounds[2] - bounds[0]
                height = bounds[3] - bounds[1]
                # Look for tall, wide containers (list-like dimensions)
                # These might be RecyclerView, ListView, etc. not marked as scrollable
                if width > 200 and height > 300:  # Large enough to be a list
                    containers.append(node)

        return containers

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
        """Find first visible item in a container using hierarchy parent relationships."""
        cx1, cy1, cx2, cy2 = container_bounds

        nodes = observation.get('nodes', [])
        if not nodes:
            return None

        # Find the container node itself
        container_node_idx = None
        for idx, node in enumerate(nodes):
            nx1, ny1, nx2, ny2 = node.get('bounds', [0, 0, 0, 0])
            if nx1 == cx1 and ny1 == cy1 and nx2 == cx2 and ny2 == cy2:
                container_node_idx = idx
                break

        # If we found the container, look for its direct children
        candidates = []
        if container_node_idx is not None:
            # Find all direct children of the container
            for idx, node in enumerate(nodes):
                if node.get('parent') == container_node_idx:
                    nx1, ny1, nx2, ny2 = node.get('bounds', [0, 0, 0, 0])
                    width = nx2 - nx1
                    height = ny2 - ny1

                    # Items should be substantial and visible
                    if width > 50 and height > 50 and ny2 > cy1:
                        candidates.append((nx1, ny1, nx2, ny2))

        # If direct children search didn't work, fall back to bounds-based search.
        # Exclude the container itself and other near-full-container wrappers;
        # otherwise the assertion crop becomes almost the entire screen.
        if not candidates:
            for node in nodes:
                nx1, ny1, nx2, ny2 = node.get('bounds', [0, 0, 0, 0])
                width = nx2 - nx1
                height = ny2 - ny1
                container_width=cx2-cx1
                container_height=cy2-cy1
                same_as_container=(nx1,ny1,nx2,ny2)==(
                    cx1,cy1,cx2,cy2)

                # Item must be substantial and within container
                if (not same_as_container and
                    width >= container_width * .55 and
                    50 < height < container_height * .75 and
                    nx1 >= cx1 and nx2 <= cx2 and
                    ny2 > cy1 and ny1 < cy2):
                    candidates.append((nx1, ny1, nx2, ny2))

        if not candidates:
            return None

        # Return topmost item (first visible)
        return min(candidates, key=lambda item: (max(item[1], cy1), item[0]))

    def _expand_label_bounds(
        self,
        label_bounds: List[int],
        item_bounds: Tuple[int,int,int,int],
        screenshot_dims: Tuple[int,int]
    ) -> List[int]:
        """Add enough item context for reliable OCR/model label inspection."""
        x1,y1,x2,y2=label_bounds
        ix1,iy1,ix2,iy2=item_bounds
        screen_width,screen_height=screenshot_dims
        label_width=max(1,x2-x1)
        label_height=max(1,y2-y1)
        target_width=max(220,label_width*2)
        target_height=max(140,label_height*4)
        center_x=(x1+x2)//2
        center_y=(y1+y2)//2
        left=max(ix1,center_x-target_width//2)
        top=max(iy1,center_y-target_height//2)
        right=min(ix2,screen_width,left+target_width)
        bottom=min(iy2,screen_height,top+target_height)
        left=max(ix1,right-target_width)
        top=max(iy1,bottom-target_height)
        return [left,top,right,bottom]

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
