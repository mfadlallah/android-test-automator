"""Reusable capability contract shared by planning and execution."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    roles: frozenset
    requires_target: bool = False
    requires_value: bool = False
    requires_direction: bool = False
    description: str = ''


REGISTRY = {
    spec.name:spec for spec in (
        CapabilitySpec(
            'tap',frozenset({'action'}),requires_target=True,
            description='Tap a visible semantic target.'),
        CapabilitySpec(
            'recover_optional',frozenset({'recovery'}),
            description='Allow bounded recovery of optional foreground UI.'),
        CapabilitySpec(
            'set_control',frozenset({'setup','action'}),
            requires_target=True,requires_value=True,
            description='Select a value in a segmented or toggle control.'),
        CapabilitySpec(
            'assert_changed',frozenset({'assertion'}),requires_target=True,
            description='Require observed geometry or content change.'),
        CapabilitySpec(
            'scroll',frozenset({'action'}),requires_target=True,
            requires_direction=True,
            description='Scroll a grounded container.'),
        CapabilitySpec(
            'assert_scrolled',frozenset({'assertion'}),requires_target=True,
            description='Require content movement or newly exposed content.'),
        CapabilitySpec(
            'assert_visible',frozenset({'assertion'}),requires_target=True,
            description='Require a semantic target to be visible.'),
        CapabilitySpec(
            'assert_contains',frozenset({'assertion'}),requires_target=True,
            requires_value=True,
            description='Require a target region to contain a value.'),
        CapabilitySpec(
            'assert_not_contains',frozenset({'assertion'}),requires_target=True,
            requires_value=True,
            description='Require a target region not to contain a value.'),
        CapabilitySpec(
            'assert_selected',frozenset({'assertion'}),requires_target=True,
            description='Require an option to expose selected state.'),
        CapabilitySpec(
            'assert_hidden',frozenset({'assertion'}),requires_target=True,
            description='Require a semantic target to be absent.'),
        CapabilitySpec(
            'wait_changed',frozenset({'assertion'}),requires_target=True,
            description='Wait for a target region to finish loading or change.'),
    )
}


def capability_names():
    return tuple(REGISTRY)


def capability_catalog():
    """Canonical AI-facing ontology; language maps into these contracts."""
    return [
        {
            'name':spec.name,
            'roles':sorted(spec.roles),
            'requires_target':spec.requires_target,
            'requires_value':spec.requires_value,
            'requires_direction':spec.requires_direction,
            'description':spec.description,
        }
        for spec in REGISTRY.values()
    ]


def validate_capability_step(step):
    """Return None or a stable validation error string."""
    spec=REGISTRY.get(step.get('capability'))
    if spec is None:
        return 'Unsupported capability: '+str(step.get('capability'))
    if step.get('role') not in spec.roles:
        return spec.name+' does not allow role '+str(step.get('role'))+'.'
    if spec.requires_target and not step.get('target'):
        return spec.name+' requires a semantic target.'
    if spec.requires_value and not step.get('value'):
        return spec.name+' requires a value.'
    if spec.requires_direction and step.get('direction')=='none':
        return spec.name+' requires a direction.'
    return None
