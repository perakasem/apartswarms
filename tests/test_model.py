"""The formal model (review Section 2) reproduced exactly."""

import numpy as np
import pytest

from sas.params import (Payoffs, o_draw_payoff_gap, perceived_value, rho_star, table1,
                        violation_rate, worker_profiles)

PAY = Payoffs(10, 5, 40)


def test_table1_matches_review():
    rows = {r["type"]: r for r in table1(0.25, PAY)}
    expect = {  # type: (q, viol, U(0), U(0.375), U(1))  -- review Table 1
        "careful": (0.2625, 0.025, 6.06, 5.69, 5.06),
        "complier": (0.0625, 0.225, 9.06, 5.69, 0.06),
        "over_refuser": (0.5250, 0.025, 2.13, 1.75, 1.13),
        "random_objector": (0.2625, 0.184, 6.06, 3.30, -1.31),
    }
    for t, (q, viol, u0, us, u1) in expect.items():
        r = rows[t]
        assert r["q"] == pytest.approx(q, abs=1e-4)
        assert r["violation_rate"] == pytest.approx(viol, abs=1e-3)
        assert r["U_rho0"] == pytest.approx(u0, abs=0.01)
        assert r["U_rhostar"] == pytest.approx(us, abs=0.01)
        assert r["U_true"] == pytest.approx(u1, abs=0.01)


def test_rho_star_and_band():
    assert rho_star(PAY) == pytest.approx(0.375)
    assert rho_star(Payoffs(10, 15, 40)) == pytest.approx(0.625)   # high-friction level
    prof = worker_profiles(0.25)
    for rho, careful_wins in [(0.0, False), (0.25, False), (0.5, True), (1.0, True)]:
        diff = perceived_value(prof["careful"], 0.25, rho, PAY) - perceived_value(prof["complier"], 0.25, rho, PAY)
        assert (diff > 0) == careful_wins


def test_eq3_audit_gap():
    prof = worker_profiles(0.25)
    for rho in np.linspace(0, 1, 11):
        lhs = perceived_value(prof["careful"], 0.25, rho, PAY) - perceived_value(prof["complier"], 0.25, rho, PAY)
        assert lhs == pytest.approx(0.25 * (0.9 - 0.1) * (rho * 40 - 15))


def test_over_refuser_gap_is_rho_free():
    prof = worker_profiles(0.25)
    for rho in (0, 0.25, 0.5, 1):
        gap = perceived_value(prof["careful"], 0.25, rho, PAY) - perceived_value(prof["over_refuser"], 0.25, rho, PAY)
        assert gap == pytest.approx(3.9375)   # review 2.5: ~3.94


@pytest.mark.parametrize("pi", [0.15, 0.25, 0.35])
def test_random_objector_matched_at_every_pi(pi):
    prof = worker_profiles(pi)
    assert prof["random_objector"].q(pi) == pytest.approx(prof["careful"].q(pi))
    assert prof["random_objector"].r == prof["random_objector"].f
    assert perceived_value(prof["random_objector"], pi, 0, PAY) == pytest.approx(
        perceived_value(prof["careful"], pi, 0, PAY))


def test_o_draw_gap_section_2_8():
    for rho in (0, 0.375, 1):
        assert o_draw_payoff_gap(0.25, rho, PAY) == pytest.approx(-12 + 32 * rho)


def test_eq7_uniform_violation_scale():
    prof = worker_profiles(0.25)
    v_uniform = np.mean([violation_rate(p, 0.25) for p in prof.values()])
    assert v_uniform == pytest.approx(0.115, abs=1e-3)
    assert violation_rate(prof["complier"], 0.25) == pytest.approx(0.225)
    assert violation_rate(prof["careful"], 0.25) == pytest.approx(0.025)
