"""
dedup.py — Motor de deduplicación.

Implementa el match por 4 keys del spec:
  - source_url          (misma URL de origen)
  - profile_url         (mismo perfil público del autor)
  - patent              (misma patente, si está presente)
  - normalized_text_hash (mismo texto normalizado, aunque sea de distinto autor)

Merge strategy: keep_highest_confidence_and_latest_timestamp
  - Entre un grupo de duplicados, el caso canónico es el que tiene:
    1. Mayor score (confidence)
    2. A igual score, el timestamp más reciente
  - Los demás se marcan como duplicate_of=<canonical_case_id>, status="duplicate",
    is_canonical=False.
"""
from __future__ import annotations
from typing import List, Dict, Tuple, Set
from collections import defaultdict

from models import Case
import config


# ---------------------------------------------------------------------------
# Indexación por match key
# ---------------------------------------------------------------------------
def _match_key_values(case: Case) -> Dict[str, str]:
    """Devuelve los valores no vacíos de cada match key para el caso."""
    return {
        "source_url": case.source_url,
        "profile_url": case.profile_url,
        "patent": case.patent,
        "normalized_text_hash": case.normalized_text_hash,
    }


def build_dedup_index(cases: List[Case]) -> Dict[str, Dict[str, str]]:
    """
    Construye índices invertidos: para cada match_key, mapea valor → lista de case_ids.
    Sólo se indexan valores no vacíos.
    """
    index: Dict[str, Dict[str, List[str]]] = {k: defaultdict(list) for k in config.DEDUP_MATCH_KEYS}
    for case in cases:
        kv = _match_key_values(case)
        for key, val in kv.items():
            if val:
                index[key][val].append(case.case_id)
    return index


# ---------------------------------------------------------------------------
# Unión-find para agrupar duplicados transitivos
# ---------------------------------------------------------------------------
class UnionFind:
    def __init__(self, ids: List[str]):
        self.parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def find_duplicate_groups(cases: List[Case]) -> List[List[Case]]:
    """
    Agrupa casos duplicados por cualquiera de las 4 match keys (unión transitiva).
    Devuelve grupos de tamaño >= 2.
    """
    if not cases:
        return []
    by_id = {c.case_id: c for c in cases}
    uf = UnionFind(list(by_id.keys()))
    index = build_dedup_index(cases)

    for key in config.DEDUP_MATCH_KEYS:
        for val, ids in index[key].items():
            if len(ids) < 2:
                continue
            # Union de todos los pares en este bucket
            for i in range(1, len(ids)):
                uf.union(ids[0], ids[i])

    groups: Dict[str, List[str]] = defaultdict(list)
    for cid in by_id:
        root = uf.find(cid)
        groups[root].append(cid)

    return [[by_id[cid] for cid in group] for group in groups.values() if len(group) >= 2]


# ---------------------------------------------------------------------------
# Merge strategy
# ---------------------------------------------------------------------------
def pick_canonical(group: List[Case]) -> Case:
    """
    Elige el caso canónico del grupo:
    1. Mayor score
    2. A igual score, timestamp más reciente
    """
    return max(group, key=lambda c: (c.score, c.timestamp))


def merge_duplicates(cases: List[Case]) -> Tuple[List[Case], int]:
    """
    Aplica dedup a la lista de casos.

    Returns:
        cases_processed: lista con todos los casos (canónicos + duplicados marcados)
        duplicates_found: cantidad de duplicados marcados
    """
    groups = find_duplicate_groups(cases)
    duplicates_found = 0

    # Mapear cada case_id a su canonical
    canonical_map: Dict[str, str] = {}
    for group in groups:
        canonical = pick_canonical(group)
        for case in group:
            if case.case_id != canonical.case_id:
                canonical_map[case.case_id] = canonical.case_id

    # Aplicar marcas
    for case in cases:
        if case.case_id in canonical_map:
            case.duplicate_of = canonical_map[case.case_id]
            case.is_canonical = False
            case.status = "duplicate"
            duplicates_found += 1
        else:
            case.is_canonical = True

    # Agregar a cada canónico la lista de case_ids que duplicó
    for group in groups:
        canonical = pick_canonical(group)
        canonical.duplicates = [c.case_id for c in group if c.case_id != canonical.case_id]

    return cases, duplicates_found


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from mock_sources import generate_mock_signals
    from extractor import signal_to_case
    from scorer import update_case_score

    sigs = generate_mock_signals()
    cases = []
    for s in sigs:
        case, status = signal_to_case(s)
        if case:
            update_case_score(case)
            cases.append(case)

    print(f"Antes de dedup: {len(cases)} casos")
    cases, ndup = merge_duplicates(cases)
    canonical = [c for c in cases if c.is_canonical]
    print(f"Después de dedup: {len(canonical)} canónicos, {ndup} duplicados marcados\n")

    print("Duplicados:")
    for c in cases:
        if not c.is_canonical:
            print(f"  {c.case_id} → duplicate_of={c.duplicate_of} | {c.problem_type} | {c.jurisdiction}")
