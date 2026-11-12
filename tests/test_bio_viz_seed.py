"""Static checks for BioViz recipe seed data."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from bio_viz.seed_data import RECIPES, STYLES


class BioVizSeedTests(unittest.TestCase):
    def test_recipe_ids_are_unique(self) -> None:
        ids = [recipe["recipe_id"] for recipe in RECIPES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_recipe_has_style_and_compilable_code(self) -> None:
        styles = {style["style_id"] for style in STYLES}
        for recipe in RECIPES:
            self.assertIn(recipe["style_id"], styles)
            compile(recipe["code"], recipe["recipe_id"], "exec")

    def test_queries_reference_existing_recipes(self) -> None:
        ids = {recipe["recipe_id"] for recipe in RECIPES}
        queries = json.loads(Path(__file__).resolve().parent.parent.joinpath("bio_viz/queries.json").read_text(encoding="utf-8"))
        self.assertEqual(len(queries), 12)
        for case in queries:
            self.assertIn(case["expected"], ids)


if __name__ == "__main__":
    unittest.main()
