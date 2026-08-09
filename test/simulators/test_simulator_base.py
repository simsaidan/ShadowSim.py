import numpy as np
import pytest

from shadowsim.core import Hamiltonian, Operator, State
from shadowsim.simulators import QutipSimulator
from shadowsim.simulators.simulator import Simulator

Z = np.diag([1.0, -1.0]).astype(np.complex128)


def _tiny_qutip():
    return QutipSimulator(
        [Hamiltonian(Z)],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        [Operator(Z)],
        1,
        0.1,
        3,
    )


def test_qutip_simulator_str_and_repr():
    sim = _tiny_qutip()
    text = str(sim)
    rep = repr(sim)
    assert "QutipSimulator(" in text
    assert "num_qubits=1" in text
    assert "observable_count=1" in text
    assert "QutipSimulator(" in rep
    assert "time_steps=3" in rep


def test_simulator_rejects_empty_hamiltonians():
    with pytest.raises(ValueError, match="non-empty list"):
        Simulator(
            [],
            [],
            State(np.array([1.0, 0.0], dtype=np.complex128), 1),
            1,
            1.0,
            2,
            "base",
        )


def test_simulator_base_simulate_not_implemented():
    sim = Simulator(
        [Hamiltonian(Z)],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        1.0,
        2,
        "base",
    )
    with pytest.raises(NotImplementedError, match="Subclasses must implement"):
        sim.simulate()


def test_simulator_get_results_requires_run():
    sim = Simulator(
        [Hamiltonian(Z)],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        1.0,
        2,
        "base",
    )
    with pytest.raises(ValueError, match="Results are not available"):
        sim.get_results()


def test_simulator_plot_and_save_result_plot(tmp_path, monkeypatch):
    class Tiny(Simulator):
        def simulate(self):
            self.results = [np.linspace(0.0, 1.0, self.time_steps)]

    monkeypatch.chdir(tmp_path)
    sim = Tiny(
        [Hamiltonian(Z)],
        [],
        State(np.array([1.0, 0.0], dtype=np.complex128), 1),
        1,
        1.0,
        3,
        "tiny",
    )
    sim.run()

    shown = {"called": False}

    def fake_show():
        shown["called"] = True

    monkeypatch.setattr("shadowsim.simulators.simulator.plt.show", fake_show)
    sim.plot_results(labels=["pop"], title="demo")
    assert shown["called"]
    sim.plot_results(indices=[0])  # explicit indices, no title

    # Defaults: indices=None, no title.
    path = sim.save_result_plot(dpi=80)
    assert path.is_file()
    assert "tiny_" in path.name

    # Explicit indices + title hit the remaining branch edges.
    path2 = sim.save_result_plot(indices=[0], dpi=80, title="saved", labels=["pop"])
    assert path2.is_file()

    text = str(sim)
    rep = repr(sim)
    assert "Tiny(" in text
    assert "id=tiny" in text
    assert "Tiny(" in rep
