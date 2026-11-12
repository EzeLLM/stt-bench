import { test, expect } from "@playwright/test";
import {
  moveTo,
  normalizeTies,
  orderFromRanks,
  ranksFromOrder,
  shift,
} from "../src/ranking";

test("ranks load into an ordered list with ties and an unranked tray", () => {
  const { ranked, unranked, tied } = orderFromRanks(["a", "b", "c", "d"], {
    a: 3,
    b: 1,
    c: 1,
    d: null,
  });
  expect(ranked).toEqual(["b", "c", "a"]);
  expect(unranked).toEqual(["d"]);
  expect([...tied]).toEqual(["c"]);
});

test("competition ranking skips places after a tie", () => {
  expect(ranksFromOrder(["b", "c", "a"], new Set(["c"]))).toEqual({
    b: 1,
    c: 1,
    a: 3,
  });
  expect(ranksFromOrder(["x"], new Set(["x"]))).toEqual({ x: 1 });
});

test("moving a card lands before the target going up and after it going down", () => {
  expect(moveTo(["a", "b", "c"], "c", "a")).toEqual(["c", "a", "b"]);
  expect(moveTo(["a", "b", "c"], "a", "c")).toEqual(["b", "c", "a"]);
  expect(moveTo(["a", "b"], "c", null)).toEqual(["a", "b", "c"]);
  expect(moveTo(["a", "b"], "c", "b")).toEqual(["a", "c", "b"]);
});

test("shift moves one place and stops at the ends", () => {
  expect(shift(["a", "b", "c"], "b", -1)).toEqual(["b", "a", "c"]);
  expect(shift(["a", "b", "c"], "a", -1)).toEqual(["a", "b", "c"]);
  expect(shift(["a", "b", "c"], "c", 1)).toEqual(["a", "b", "c"]);
});

test("a tie flag never survives on the first card or on unranked cards", () => {
  expect([...normalizeTies(["a", "b"], new Set(["a", "b", "z"]))]).toEqual([
    "b",
  ]);
});
