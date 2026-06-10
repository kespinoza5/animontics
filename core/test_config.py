"""Unit tests for the fleet config merge — address comes from the access layer."""
from core.config import _merge
from core.models import AnimonNodeAccess, NodeDesiredState


def test_hostname_and_port_come_from_access():
    desired = NodeDesiredState(id="n1", type="orangepi_zero2", role="proprioception")
    access = AnimonNodeAccess(ip="192.168.1.140", hostname="orangepi",
                              port=9090, ssh_user="orangepi")
    entry = _merge(desired, access)
    # Address is authored in the access layer, not desired state.
    assert entry.hostname == "orangepi"
    assert entry.port == 9090
    assert entry.ip == "192.168.1.140"
    # Desired-state fields still come from desired state.
    assert entry.role == "proprioception"


def test_port_defaults_to_8080_when_unset():
    entry = _merge(
        NodeDesiredState(id="n2", type="raspberry_pi_5"),
        AnimonNodeAccess(ip="192.168.1.10"),
    )
    assert entry.port == 8080
    assert entry.hostname is None


def test_desired_state_has_no_network_fields():
    # Desired state is pure logic — the address fields were removed from the model.
    fields = NodeDesiredState.model_fields
    assert "hostname" not in fields
    assert "port" not in fields
