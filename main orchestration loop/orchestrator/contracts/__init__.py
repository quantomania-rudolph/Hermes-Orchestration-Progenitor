"""Phase transition contracts (T29)."""

from orchestrator.contracts import (
    transition_p0_p1,
    transition_p1_p2,
    transition_p2_p3,
    transition_p3_p4,
    transition_p4_p5,
    transition_p5_p1,
    transition_p5_done,
)
from tools.orchestration.t29_phase_controller import PhaseTransitionController, TransitionContract


def register_all(controller: PhaseTransitionController) -> None:
    pairs = [
        ("P0_to_P1", transition_p0_p1),
        ("P1_to_P2", transition_p1_p2),
        ("P2_to_P3", transition_p2_p3),
        ("P3_to_P4", transition_p3_p4),
        ("P4_to_P5", transition_p4_p5),
        ("P5_to_P1", transition_p5_p1),
        ("P5_to_DONE", transition_p5_done),
    ]
    for name, mod in pairs:
        controller.register(TransitionContract(name, mod.check_entry, mod.assert_exit))
