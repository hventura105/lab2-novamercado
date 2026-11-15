"""Invariantes matemáticas y temporales, con fixtures efímeras distintas de fuentes oficiales."""

from datetime import date, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from app.core.temporal import Sale, TemporalLeakageError, assert_model_available, available_sales, chronological_split, past_features, validate_forecast_date
from app.services.costos import business_cost, suggested_quantity, technical_metrics


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.target = date(2025, 3, 3)
        self.past = Sale(1, "a", self.target - timedelta(days=1), 12)

    def test_current_and_future_observations_are_never_features(self):
        future = [Sale(1, "a", self.target + timedelta(days=offset), 999999) for offset in (0, 1, 20)]
        before = past_features([self.past], 1, "a", self.target)
        after = past_features([self.past, *future], 1, "a", self.target)
        self.assertEqual(before, after)
        self.assertEqual(available_sales([self.past, *future], self.target), [self.past])

    def test_model_trained_on_same_or_future_day_is_rejected(self):
        for offset in (0, 1, 20):
            with self.assertRaises(TemporalLeakageError):
                assert_model_available(self.target + timedelta(days=offset), self.target)
        assert_model_available(self.past.fecha, self.target)

    def test_missing_day_is_not_zero_sale(self):
        row = Sale(1, "a", self.target - timedelta(days=3), 12)
        features = past_features([row], 1, "a", self.target)
        self.assertIsNone(features["lag_1"])
        self.assertEqual(features["observaciones_7"], 1)
        self.assertEqual(features["dias_desde_ultima"], 3)

    def test_other_store_or_family_does_not_leak(self):
        rows = [self.past, Sale(2, "a", self.past.fecha, 900), Sale(1, "b", self.past.fecha, 800)]
        self.assertEqual(past_features(rows, 1, "a", self.target)["media_7"], 12)

    def test_unknown_promotions_remain_missing(self):
        self.assertIsNone(self.past.en_promocion)

    def test_split_groups_all_series_by_day(self):
        rows = [Sale(store, "a", self.target + timedelta(days=offset), 1) for offset in range(10) for store in (1, 2)]
        train, validation = chronological_split(reversed(rows), 3)
        self.assertLess(max(row.fecha for row in train), min(row.fecha for row in validation))
        self.assertEqual(len(validation), 6)

    def test_dates_use_source_boundaries_and_not_wall_clock(self):
        validate_forecast_date(date(2001, 1, 2), date(2001, 1, 1), date(2001, 2, 1))
        validate_forecast_date(date(2099, 1, 2), date(2099, 1, 1), date(2099, 2, 1))
        with self.assertRaises(ValueError):
            validate_forecast_date(date(2001, 3, 1), date(2001, 1, 1), date(2001, 2, 1))


class CostTests(unittest.TestCase):
    def test_official_formula(self):
        self.assertEqual(business_cost(10, 7, 5, 2), 15)
        self.assertEqual(business_cost(10, 12, 5, 2), 4)

    def test_integer_solution_matches_exhaustive_minimum(self):
        observations = [0, 1.2, 2.5, 4, 9.1]
        for missing, surplus in ((1, 9), (9, 1), (1, 1), (0, 1), (1, 0)):
            suggested = suggested_quantity(observations, missing, surplus)
            cost = lambda q: sum(business_cost(value, q, missing, surplus) for value in observations)
            self.assertEqual(cost(suggested), min(cost(quantity) for quantity in range(12)))
            self.assertIs(type(suggested), int)

    def test_more_expensive_shortages_increase_inventory(self):
        values = [0, 10, 20, 30, 40]
        self.assertLessEqual(suggested_quantity(values, 1, 9), suggested_quantity(values, 9, 1))

    def test_no_invented_demand_when_observations_absent(self):
        with self.assertRaises(ValueError):
            suggested_quantity([], 1, 1)

    def test_invalid_costs_and_quantities_are_rejected(self):
        for quantity in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                business_cost(10, quantity, 1, 1)
        with self.assertRaises(ValueError):
            suggested_quantity([1], 0, 0)
        with self.assertRaises(ValueError):
            suggested_quantity([float("nan")], 1, 1)

    def test_metrics(self):
        result = technical_metrics([0, 10], [2, 8])
        self.assertEqual(result, {"mae": 2, "rmse": 2})


if __name__ == "__main__":
    unittest.main()
