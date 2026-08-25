"""Tests for landmarks.py — GPS-derived river miles."""
import pytest

from landmarks import (
    LANDMARK_COORDS,
    LANDMARK_MILES,
    WHITE_HOLE_MILE,
    haversine_miles,
)


class TestLandmarkMiles:
    def test_dam_at_zero_and_white_hole_at_calibrated_distance(self):
        miles = dict(LANDMARK_MILES)
        assert miles["Bull Shoals Dam"] == 0.0
        assert miles["The White Hole"] == WHITE_HOLE_MILE == 7.0

    def test_miles_strictly_increase_downstream(self):
        values = [mile for _, mile in LANDMARK_MILES]
        assert values == sorted(values)
        assert len(set(values)) == len(values)

    def test_same_landmarks_same_order_as_coords(self):
        assert [n for n, _ in LANDMARK_MILES] == [n for n, _ in LANDMARK_COORDS]

    def test_gps_derived_positions(self):
        """Spot-check the scaled chord distances against the pinned GPS chain."""
        miles = dict(LANDMARK_MILES)
        assert miles["White River State Park"] == pytest.approx(1.34)
        assert miles["Gaston's"] == pytest.approx(4.09)
        assert miles["Big Island"] == pytest.approx(6.25)

    def test_haversine_known_distance(self):
        # Dam to White River State Park chord is about 1.29 miles
        dist = haversine_miles(
            dict(LANDMARK_COORDS)["Bull Shoals Dam"],
            dict(LANDMARK_COORDS)["White River State Park"],
        )
        assert dist == pytest.approx(1.29, abs=0.01)
