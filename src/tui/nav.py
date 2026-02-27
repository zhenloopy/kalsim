from textual.binding import Binding
from textual.widgets import Tabs, DataTable, TabbedContent, TabPane
from textual.containers import Horizontal

NAV_BINDINGS = [
    Binding("down", "nav('down')", show=False, priority=True),
    Binding("up", "nav('up')", show=False, priority=True),
    Binding("left", "nav('left')", show=False, priority=True),
    Binding("right", "nav('right')", show=False, priority=True),
]


class PageNavMixin:
    """Mixin for Textual App: spatial arrow-key navigation through the widget tree.

    Usage:
        class MyApp(PageNavMixin, App):
            BINDINGS = [*other_bindings, *NAV_BINDINGS]

    Vertical containers use up/down to move between children.
    Horizontal containers use left/right.
    When a widget is at its boundary, navigation walks up the DOM tree
    looking for a sibling in the matching layout direction.

    Down from tabs enters the active tab pane.
    Up from the top of a pane returns to tabs.
    Set nav_skip = True on any widget to exclude it from arrow navigation.
    """

    def _container_direction(self, widget) -> str:
        if isinstance(widget, Horizontal):
            return "horizontal"
        return "vertical"

    def _nav_children(self, container) -> list:
        return [
            c for c in container.children
            if not getattr(c, "nav_skip", False)
            and (c.can_focus or self._has_focusable(c))
        ]

    def _has_focusable(self, widget) -> bool:
        for w in widget.query("*"):
            if w.can_focus and not getattr(w, "nav_skip", False):
                return True
        return False

    def _entry_widget(self, widget, direction: str):
        """Recursively find the focusable to land on when entering a container."""
        if widget.can_focus:
            if isinstance(widget, DataTable) and direction == "up" and widget.row_count > 0:
                widget.move_cursor(row=widget.row_count - 1, animate=False)
            return widget
        children = self._nav_children(widget)
        if not children:
            return None
        ordered = reversed(children) if direction in ("up", "left") else iter(children)
        for child in ordered:
            result = self._entry_widget(child, direction)
            if result:
                return result
        return None

    def _at_boundary(self, widget, direction: str) -> bool:
        if isinstance(widget, DataTable):
            if direction == "up":
                return widget.cursor_row <= 0 or widget.row_count == 0
            if direction == "down":
                return widget.cursor_row >= widget.row_count - 1 or widget.row_count == 0
            return True
        if direction in ("up", "down") and hasattr(widget, "scroll_y"):
            if direction == "up":
                return widget.scroll_y <= 0
            return widget.scroll_y >= widget.max_scroll_y
        if direction in ("left", "right") and hasattr(widget, "scroll_x"):
            if direction == "left":
                return widget.scroll_x <= 0
            return widget.scroll_x >= widget.max_scroll_x
        return True

    def _find_nav_target(self, widget, direction: str):
        """Walk up the DOM to find a spatial neighbor in the given direction."""
        current = widget
        while current is not None:
            if isinstance(current, TabPane):
                break
            parent = current.parent
            if parent is None:
                break
            layout = self._container_direction(parent)
            matches = (
                direction in ("up", "down") and layout == "vertical"
                or direction in ("left", "right") and layout == "horizontal"
            )
            if matches:
                siblings = self._nav_children(parent)
                idx = next((i for i, s in enumerate(siblings) if s is current), -1)
                if idx >= 0:
                    target_idx = idx + (1 if direction in ("down", "right") else -1)
                    if 0 <= target_idx < len(siblings):
                        return self._entry_widget(siblings[target_idx], direction)
            current = parent
        return None

    def _forward_key(self, widget, direction: str) -> None:
        actions = {
            "down":  ("action_cursor_down",  "action_scroll_down"),
            "up":    ("action_cursor_up",    "action_scroll_up"),
            "right": ("action_cursor_right", "action_scroll_right"),
            "left":  ("action_cursor_left",  "action_scroll_left"),
        }
        for action in actions.get(direction, ()):
            if hasattr(widget, action):
                getattr(widget, action)()
                return

    def _get_active_pane(self) -> TabPane | None:
        try:
            tc = self.query_one(TabbedContent)
            return tc.query_one(f"TabPane#{tc.active}")
        except Exception:
            return None

    def _is_inside(self, widget, ancestor) -> bool:
        current = widget
        while current:
            if current is ancestor:
                return True
            current = current.parent
        return False

    def action_nav(self, direction: str) -> None:
        focused = self.focused
        if focused is None:
            return

        if isinstance(focused, Tabs):
            if direction == "down":
                pane = self._get_active_pane()
                if pane:
                    target = self._entry_widget(pane, direction)
                    if target:
                        target.focus()
            elif direction == "left":
                focused.action_previous_tab()
            elif direction == "right":
                focused.action_next_tab()
            return

        if not self._at_boundary(focused, direction):
            self._forward_key(focused, direction)
            return

        target = self._find_nav_target(focused, direction)
        if target:
            target.focus()
            return

        if direction == "up":
            pane = self._get_active_pane()
            if pane and self._is_inside(focused, pane):
                try:
                    self.query_one(Tabs).focus()
                except Exception:
                    pass
            return

        self._forward_key(focused, direction)
