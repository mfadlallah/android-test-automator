"""Plan-based terminal progress; observation budgets are not step counts."""

class PlanProgress:
    def __init__(self, plan, emit=print):
        self.steps = plan['steps']
        self.emit = emit
        self.displayed = None

    def show(self, index):
        if index == self.displayed or not 0 <= index < len(self.steps):
            return
        step = self.steps[index]
        description = step['capability'].replace('_', ' ')
        if step.get('target'):
            description += ': ' + str(step['target'])
        if step.get('value'):
            description += ' → ' + str(step['value'])
        self.emit(f'[{index + 1}/{len(self.steps)}] {description}')
        self.displayed = index

    def find(self, capability, role=None):
        return next((i for i, step in enumerate(self.steps)
                     if step['capability'] == capability
                     and (role is None or step.get('role') == role)), None)

    def detail(self, decision, completed=False, recovery=False):
        action = decision['action']
        prefix = (action.upper() + ': ' if action in {'failed', 'blocked'}
                  else '↳ Wait: ' if action == 'wait'
                  else '↳ Recovery: ' if recovery
                  else '✓ ' if completed else '↳ ')
        self.emit('  ' + prefix + decision['reason'])

    def legacy(self, decision, usage):
        """Translate existing executor events to plan positions for display only."""
        source = usage.get('source', '')
        action = decision['action']
        recovery = source in {
            'recovery', 'hour_offer_gate', 'delivery_address_gate',
            'in_app_message_gate', 'unexpected_modal_back_gate',
            'optional_grounding_back_fallback'}
        capability, role = 'tap', 'action'
        if source.startswith('layout_precondition'):
            capability, role = 'set_control', 'setup'
        elif source in {'layout_toggle_gate', 'layout_toggle_verification_wait'}:
            capability, role = 'set_control', 'action'
            if source == 'layout_toggle_verification_wait':
                capability, role = 'assert_changed', None
        elif source == 'layout_toggle_verified':
            index = self.find('assert_changed')
            if index is not None:
                self.show(index)
                self.emit('  ✓ ' + usage.get('layout_evidence', decision['evidence']))
            capability, role = ('scroll', None) if action in {'scroll', 'screen_scroll'} else ('assert_changed', None)
        elif source == 'screenshot_scroll_fallback' or action in {'scroll', 'screen_scroll', 'passed'}:
            capability, role = ('assert_scrolled', None) if action in {'passed', 'blocked'} else ('scroll', None)
        if recovery:
            if self.displayed is None:
                self.show(0)
        else:
            index = self.find(capability, role)
            if index is not None:
                # A legacy recovery phase finishes when the next planned action
                # becomes executable; this is display, not assertion evidence.
                optional = self.find('recover_optional')
                if optional is not None and (self.displayed or 0) < optional < index:
                    self.show(optional)
                    self.emit('  ↳ Continuing with the next planned action.')
                self.show(index)
        self.detail(decision, completed=action in {'tap', 'scroll', 'screen_scroll', 'passed'} and not recovery,
                    recovery=recovery)
