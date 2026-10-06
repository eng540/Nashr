export function toggleSelection(selected: string[], id: string, checked: boolean): string[] {
  const next = checked ? [...selected, id] : selected.filter((selectedId) => selectedId !== id);
  return [...new Set(next)];
}

export function selectionFromQuery(raw: string | null): string[] {
  if (!raw) return [];
  return [...new Set(raw.split(",").map((id) => id.trim()).filter(Boolean))];
}
