"""Agreement metrics checked against published worked examples.

Each expected value is the number the cited source prints, asserted to the
precision it is printed at.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from molabel.core.quality.agreement_metrics import (
    AgreementAnnotation,
    AgreementMetricsService,
    AgreementRecord,
)

KRIPPENDORFF_2011 = (
    "Krippendorff, K. (2011). Computing Krippendorff's Alpha-Reliability. "
    "Departmental Papers (ASC) 43, University of Pennsylvania. "
    "Version 2011.1.25, literature updated 2013.9.13."
)

PRINTED_TO_3_DECIMALS = 5e-4
PRINTED_TO_2_DECIMALS = 5e-3


def _records(
    reliability_data: Sequence[Sequence[str | None]],
    sources: Sequence[str],
) -> list[AgreementRecord]:
    """One record per unit (column); row i holds rater i's values, None if missing."""
    units = zip(*reliability_data, strict=True)
    return [
        AgreementRecord(
            record_id=f"u{index}",
            annotations=[
                AgreementAnnotation(
                    source=source,
                    labels={} if value is None else {"code": value},
                )
                for source, value in zip(sources, unit, strict=True)
            ],
        )
        for index, unit in enumerate(units, start=1)
    ]


def _split(row: str) -> list[str | None]:
    return [None if value == "." else value for value in row.split()]


def test_alpha_matches_krippendorff_2011_binary_two_observers() -> None:
    """KRIPPENDORFF_2011, section A, pp. 2-3: Meg and Owen, 10 units, alpha = 0.095."""
    meg = _split("0 1 0 0 0 0 0 0 1 0")
    owen = _split("1 1 1 0 0 1 0 0 0 0")

    result = AgreementMetricsService().analyze(
        _records([meg, owen], ["human", "human"]),
        analysis_type="inter_annotator",
    )

    assert result.overall.krippendorff_alpha == pytest.approx(
        0.095, abs=PRINTED_TO_3_DECIMALS
    )


def test_alpha_matches_krippendorff_2011_nominal_two_observers() -> None:
    """KRIPPENDORFF_2011, section B, pp. 3-4: Ben and Gerry, 12 units, alpha = 0.692."""
    ben = _split("a a b b d c c c e d d a")
    gerry = _split("b a b b b c c c e d d d")

    result = AgreementMetricsService().analyze(
        _records([ben, gerry], ["human", "human"]),
        analysis_type="inter_annotator",
    )

    assert result.overall.krippendorff_alpha == pytest.approx(
        0.692, abs=PRINTED_TO_3_DECIMALS
    )


def test_alpha_matches_krippendorff_2011_missing_values() -> None:
    """KRIPPENDORFF_2011, section C, pp. 4-5: four observers, 12 units, 7 missing.

    alpha = 0.743. Unit 12 holds one value and is not pairable.
    """
    observers = [
        _split("1 2 3 3 2 1 4 1 2 . . ."),
        _split("1 2 3 3 2 2 4 1 2 5 . 3"),
        _split(". 3 3 3 2 3 4 2 2 5 1 ."),
        _split("1 2 3 3 2 4 4 1 2 5 1 ."),
    ]

    result = AgreementMetricsService().analyze(
        _records(observers, ["human"] * 4),
        analysis_type="inter_annotator",
    )

    assert result.overall.krippendorff_alpha == pytest.approx(
        0.743, abs=PRINTED_TO_3_DECIMALS
    )
    assert result.overall.fleiss_kappa is None
    assert "fleiss_kappa" in result.overall.null_reasons


FLEISS_1971_TABLE_1 = [
    "4 4 4 4 4 4",
    "2 2 2 5 5 5",
    "2 3 3 3 3 5",
    "5 5 5 5 5 5",
    "2 2 2 4 4 4",
    "1 1 3 3 3 3",
    "3 3 3 3 5 5",
    "1 1 3 3 3 4",
    "1 1 4 4 4 4",
    "5 5 5 5 5 5",
    "1 4 4 4 4 4",
    "1 2 4 4 4 4",
    "2 2 2 3 3 3",
    "1 4 4 4 4 4",
    "2 2 4 4 4 5",
    "3 3 3 3 3 5",
    "1 1 1 4 5 5",
    "1 1 1 1 1 2",
    "2 2 4 4 4 4",
    "1 3 3 5 5 5",
    "5 5 5 5 5 5",
    "2 4 4 4 4 4",
    "2 2 4 5 5 5",
    "1 1 4 4 4 4",
    "1 4 4 4 4 5",
    "2 2 2 2 2 4",
    "1 1 1 1 5 5",
    "2 2 4 4 4 4",
    "1 3 3 3 3 3",
    "5 5 5 5 5 5",
]


def test_fleiss_kappa_matches_fleiss_1971_table_1() -> None:
    """Fleiss, J. L. (1971). Measuring nominal scale agreement among many raters.

    Psychological Bulletin, 76(5), 378-382. Table 1: 30 patients, six psychiatric
    diagnoses each, five categories. Fleiss reports kappa = .430.

    The rows are the R irr package's `diagnoses` dataset, which irr documents as
    the data Fleiss (1971) used. Table 1 prints their per-category counts.
    """
    subjects = [row.split() for row in FLEISS_1971_TABLE_1]
    raters = [list(column) for column in zip(*subjects, strict=True)]

    result = AgreementMetricsService().analyze(
        _records(raters, ["human"] * 6),
        analysis_type="inter_annotator",
    )

    assert result.overall.fleiss_kappa == pytest.approx(
        0.430, abs=PRINTED_TO_3_DECIMALS
    )


def test_cohen_kappa_matches_viera_garrett_2005_table_1() -> None:
    """Viera, A. J., & Garrett, J. M. (2005). Understanding interobserver agreement:

    the kappa statistic. Family Medicine, 37(5), 360-363. Table 1, p. 361: two
    residents rate 100 lectures. Resident 1 says yes 25 times, resident 2 says
    yes 20 times. The paper prints p_o = .85, p_e = .65 and kappa = .57.

    Raters are told apart by annotation source, so resident 1 is the human
    source and resident 2 the agent source.
    """
    cells = {("yes", "yes"): 15, ("no", "yes"): 5, ("yes", "no"): 10, ("no", "no"): 70}
    resident_1 = [r1 for (r1, _), count in cells.items() for _ in range(count)]
    resident_2 = [r2 for (_, r2), count in cells.items() for _ in range(count)]

    result = AgreementMetricsService().analyze(
        _records([resident_1, resident_2], ["human", "agent"]),
        analysis_type="both",
    )

    assert result.human_agent is not None
    for summary in (result.overall, result.human_agent):
        assert summary.percent_agreement == pytest.approx(0.85)
        assert summary.cohen_kappa == pytest.approx(0.57, abs=PRINTED_TO_2_DECIMALS)
        assert summary.cohen_kappa == pytest.approx((0.85 - 0.65) / (1 - 0.65))
