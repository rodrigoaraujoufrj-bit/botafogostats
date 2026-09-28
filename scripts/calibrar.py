"""
Calibragem do modelo de simulação: roda a simulação com vários valores de
ENCOLHIMENTO e imprime, para cada faixa, a pontuação que dá 50% de chance
ao Botafogo. Serve para comparar com referências externas (UFMG, GE).

Uso (precisa de FOOTBALL_DATA_TOKEN): python scripts/calibrar.py
"""

import os
import sys

import numpy as np

import coletar

VALORES = [0, 3, 6, 10, 15, 20, 30, 45]


def ponto_50(pontos: list[int], chances: list[float]) -> float | None:
    """Interpola a pontuação em que a chance cruza 50%."""
    for (p0, c0), (p1, c1) in zip(zip(pontos, chances), zip(pontos[1:], chances[1:])):
        if (c0 - 50) * (c1 - 50) <= 0 and c0 != c1:
            return round(p0 + (50 - c0) / (c1 - c0) * (p1 - p0), 1)
    return None


def main() -> int:
    token = os.environ["FOOTBALL_DATA_TOKEN"]
    df = coletar.jogos_para_dataframe(coletar.buscar(f"/competitions/{coletar.COMPETICAO}/matches", token)["matches"])
    time_id, _ = coletar.achar_time(df)
    print("encolhimento | 50%: escapar | sul-americana | libertadores(5) | g4 | titulo || chance Z4 | chance Sula")
    for e in VALORES:
        s = coletar.simular(df, time_id, encolhimento=e)
        c = s["numeros_magicos"]["chances"]
        z = {k: ponto_50(c["pontos"], c[k]) for k in ["permanencia", "sul_americana", "libertadores", "g4", "titulo"]}
        ref = {x["chave"]: x["referencia"] for x in s["numeros_magicos"]["zonas"]}
        print(f"{e:>12} | {z['permanencia']} | {z['sul_americana']} | {z['libertadores']} | {z['g4']} | "
              f"{z['titulo'] or 'ref ' + str(ref['titulo'])} || {s['prob']['z4']}% | {s['prob']['sul_americana']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
