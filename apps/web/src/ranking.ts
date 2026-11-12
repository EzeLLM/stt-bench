// Pure ranking helpers. A review's rank is stored per output; the UI works with an
// ordered list plus "tied with the card above" flags. Ranks use competition numbering
// (1, 1, 3) because the backend accepts shared ranks no larger than the output count.

export function orderFromRanks(
  ids: string[],
  ranks: Record<string, number | null | undefined>,
) {
  const ranked = ids
    .filter((id) => ranks[id])
    .sort((a, b) => ranks[a]! - ranks[b]! || ids.indexOf(a) - ids.indexOf(b));
  const tied = new Set(
    ranked.filter((id, i) => i > 0 && ranks[id] === ranks[ranked[i - 1]]),
  );
  return { ranked, unranked: ids.filter((id) => !ranks[id]), tied };
}

export function normalizeTies(ranked: string[], tied: Set<string>) {
  return new Set(ranked.slice(1).filter((id) => tied.has(id)));
}

export function ranksFromOrder(ranked: string[], tied: Set<string>) {
  const ranks: Record<string, number> = {};
  ranked.forEach((id, i) => {
    ranks[id] = i > 0 && tied.has(id) ? ranks[ranked[i - 1]] : i + 1;
  });
  return ranks;
}

// Put `id` where `target` currently sits: moving down lands after it, up lands before it.
export function moveTo(ranked: string[], id: string, target: string | null) {
  const without = ranked.filter((x) => x !== id);
  const index = target === null ? without.length : ranked.indexOf(target);
  without.splice(Math.min(index, without.length), 0, id);
  return without;
}

export function shift(ranked: string[], id: string, delta: -1 | 1) {
  const index = ranked.indexOf(id);
  const target = ranked[index + delta];
  return target === undefined ? ranked : moveTo(ranked, id, target);
}
