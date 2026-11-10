// Unit tests for pure helpers. Run with: npm test (Node's built-in test runner).
import assert from "node:assert/strict";
import { test } from "node:test";

import { formatValue, safeNext } from "../src/lib/api.ts";
import { formatPrice } from "../src/lib/directory.ts";
import { classes } from "../src/lib/sectors.ts";

test("safeNext only allows same-site paths", () => {
  assert.equal(safeNext("/explorer?area=1"), "/explorer?area=1");
  for (const bad of [null, "", "https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"]) {
    assert.equal(safeNext(bad), "/");
  }
});

test("choropleth classes have strictly increasing stops", () => {
  assert.deepEqual(classes([1, 2, 3, 4]), { stops: [1, 2, 3, 4], colors: ["#f7ede4", "#ebcfa6", "#d9a441", "#a4513a", "#6b1420"] });
  const repeated = classes([0, 0, 0, 1]);
  assert.deepEqual(repeated.stops, [0, 1]);
  assert.equal(repeated.colors.length, 3);
  assert.equal(classes([]).colors.length, 1);
});

test("prices and values format without inventing data", () => {
  assert.equal(formatPrice({ price_min_ngn: null, price_max_ngn: null, price_unit: null }), null);
  assert.equal(formatPrice({ price_min_ngn: 5000, price_max_ngn: 20000, price_unit: "per month" }), "₦5,000–₦20,000 per month");
  assert.equal(formatValue(null, "%"), "—");
  assert.equal(formatValue(61.54, "%"), "61.5%");
});
