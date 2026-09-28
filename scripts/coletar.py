"""
Coleta os jogos do Brasileirão Série A na football-data.org, calcula as
métricas da campanha do Botafogo e gera o JSON estático consumido pelo
dashboard (data/dashboard.json).

Uso:
  export FOOTBALL_DATA_TOKEN="..."
  python scripts/coletar.py

Consumo: 2 requisições por execução (jogos + classificação).
O arquivo só é reescrito quando os dados mudam, para não gerar commits vazios.
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

TEMPORADA = int(os.getenv("TEMPORADA", "2026"))
TIME_BUSCA = os.getenv("TIME_BUSCA", "Botafogo")  # trecho do nome do time
BASE = "https://api.football-data.org/v4"
COMPETICAO = "BSA"
SAIDA = Path(__file__).resolve().parent.parent / "data" / "dashboard.json"

RODADAS = 38
ENCERRADO = {"FINISHED", "AWARDED"}
CANCELADO = {"CANCELLED"}
PONTOS = {"V": 3, "E": 1, "D": 0}

N_SIMULACOES = 20_000
ENCOLHIMENTO = 6  # jogos "fictícios" na média da liga, para estabilizar a força dos times


# ----------------------------------------------------------------------------
# Coleta
# ----------------------------------------------------------------------------
def buscar(caminho: str, token: str) -> dict:
    r = requests.get(
        f"{BASE}{caminho}",
        headers={"X-Auth-Token": token},
        params={"season": TEMPORADA},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"GET {caminho} -> HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def jogos_para_dataframe(jogos: list[dict]) -> pd.DataFrame:
    linhas = []
    for m in jogos:
        ft = m["score"].get("fullTime") or {}
        ht = m["score"].get("halfTime") or {}
        linhas.append({
            "id": m["id"],
            "rodada": m.get("matchday"),
            "data": m["utcDate"],
            "status": m["status"],
            "mandante_id": m["homeTeam"]["id"],
            "mandante": m["homeTeam"].get("shortName") or m["homeTeam"]["name"],
            "mandante_escudo": m["homeTeam"].get("crest"),
            "visitante_id": m["awayTeam"]["id"],
            "visitante": m["awayTeam"].get("shortName") or m["awayTeam"]["name"],
            "visitante_escudo": m["awayTeam"].get("crest"),
            "gm": ft.get("home"),
            "gv": ft.get("away"),
            "gm_int": ht.get("home"),
            "gv_int": ht.get("away"),
        })
    df = pd.DataFrame(linhas)
    df["data"] = pd.to_datetime(df["data"], utc=True)
    df["encerrado"] = df["status"].isin(ENCERRADO) & df["gm"].notna() & df["gv"].notna()
    return df.sort_values(["data", "id"]).reset_index(drop=True)


def achar_time(df: pd.DataFrame) -> tuple[int, str]:
    nomes = pd.concat([
        df[["mandante_id", "mandante"]].set_axis(["id", "nome"], axis=1),
        df[["visitante_id", "visitante"]].set_axis(["id", "nome"], axis=1),
    ]).drop_duplicates("id")
    achados = nomes[nomes["nome"].str.contains(TIME_BUSCA, case=False, na=False)]
    if len(achados) != 1:
        raise RuntimeError(f"Esperava 1 time com '{TIME_BUSCA}' no nome, achei: {achados['nome'].tolist()}")
    return int(achados.iloc[0]["id"]), str(achados.iloc[0]["nome"])


# ----------------------------------------------------------------------------
# Visão do time
# ----------------------------------------------------------------------------
def _resultado(gp, gc) -> str:
    return "V" if gp > gc else ("E" if gp == gc else "D")


def visao_do_time(df: pd.DataFrame, time_id: int) -> pd.DataFrame:
    """Uma linha por jogo do time, do ponto de vista dele (pró / contra)."""
    t = df[(df["mandante_id"] == time_id) | (df["visitante_id"] == time_id)].copy()
    casa = t["mandante_id"] == time_id
    t["mando"] = casa.map({True: "casa", False: "fora"})
    t["adversario"] = t["visitante"].where(casa, t["mandante"])
    t["adversario_escudo"] = t["visitante_escudo"].where(casa, t["mandante_escudo"])
    t["gp"] = t["gm"].where(casa, t["gv"])
    t["gc"] = t["gv"].where(casa, t["gm"])
    t["gp_int"] = t["gm_int"].where(casa, t["gv_int"])
    t["gc_int"] = t["gv_int"].where(casa, t["gm_int"])
    t["resultado"] = [
        _resultado(gp, gc) if enc else None
        for gp, gc, enc in zip(t["gp"], t["gc"], t["encerrado"])
    ]
    t["situacao_int"] = [
        _resultado(a, b) if enc and pd.notna(a) and pd.notna(b) else None
        for a, b, enc in zip(t["gp_int"], t["gc_int"], t["encerrado"])
    ]
    t["pontos"] = t["resultado"].map(PONTOS)
    return t.reset_index(drop=True)


# ----------------------------------------------------------------------------
# Métricas de um recorte (todos / casa / fora)
# ----------------------------------------------------------------------------
def _pct(a, b):
    return round(100 * a / b, 1) if b else None


def resumo(j: pd.DataFrame) -> dict:
    n = len(j)
    v = int((j["resultado"] == "V").sum())
    e = int((j["resultado"] == "E").sum())
    d = int((j["resultado"] == "D").sum())
    pts = 3 * v + e
    gp, gc = int(j["gp"].sum()), int(j["gc"].sum())
    return {
        "jogos": n, "vitorias": v, "empates": e, "derrotas": d, "pontos": pts,
        "gols_pro": gp, "gols_contra": gc, "saldo": gp - gc,
        "aproveitamento": _pct(pts, 3 * n),
        "media_pontos": round(pts / n, 2) if n else None,
        "taxa_vitoria": _pct(v, n),
        "sem_derrota": _pct(v + e, n),
    }


def tempos(j: pd.DataFrame) -> dict:
    c = j.dropna(subset=["gp_int", "gc_int"])
    p1, c1 = int(c["gp_int"].sum()), int(c["gc_int"].sum())
    p2, c2 = int((c["gp"] - c["gp_int"]).sum()), int((c["gc"] - c["gc_int"]).sum())
    return {
        "jogos_considerados": len(c),
        "primeiro": {"pro": p1, "contra": c1, "saldo": p1 - c1, "participacao_pro": _pct(p1, p1 + p2)},
        "segundo": {"pro": p2, "contra": c2, "saldo": p2 - c2, "participacao_pro": _pct(p2, p1 + p2)},
    }


def intervalo(j: pd.DataFrame) -> dict:
    c = j.dropna(subset=["situacao_int"])
    matriz = {
        s: {r: int(((c["situacao_int"] == s) & (c["resultado"] == r)).sum()) for r in "VED"}
        for s in "VED"
    }
    p_int = c["situacao_int"].map(PONTOS)
    p_fin = c["resultado"].map(PONTOS)
    return {
        "matriz": matriz,  # linha = situação no intervalo, coluna = resultado final
        "melhoraram": int((p_fin > p_int).sum()),
        "pioraram": int((p_fin < p_int).sum()),
        "mantiveram": int((p_fin == p_int).sum()),
        "viradas_a_favor": matriz["D"]["V"],
        "viradas_contra": matriz["V"]["D"],
        "pontos_no_intervalo": int(p_int.sum()),
        "pontos_reais": int(p_fin.sum()),
        "saldo_pontos": int(p_fin.sum() - p_int.sum()),
    }


def _maior_sequencia(mascara: pd.Series) -> int:
    maior = atual = 0
    for ok in mascara:
        atual = atual + 1 if ok else 0
        maior = max(maior, atual)
    return maior


def sequencias(j: pd.DataFrame) -> dict:
    ult = j.tail(5)
    return {
        "maior_invicta": _maior_sequencia(j["resultado"] != "D"),
        "maior_vitorias": _maior_sequencia(j["resultado"] == "V"),
        "maior_sem_vencer": _maior_sequencia(j["resultado"] != "V"),
        "sem_sofrer_gol": int((j["gc"] == 0).sum()),
        "sem_marcar": int((j["gp"] == 0).sum()),
        "ultimos5": {"resultados": ult["resultado"].tolist(), "pontos": int(ult["pontos"].sum()), "disputados": 3 * len(ult)},
    }


def recorte(j: pd.DataFrame) -> dict:
    return {"resumo": resumo(j), "tempos": tempos(j), "intervalo": intervalo(j), "sequencias": sequencias(j)}


def blocos(j: pd.DataFrame, tamanho: int = 10) -> list[dict]:
    saida = []
    for i in range(0, len(j), tamanho):
        b = j.iloc[i:i + tamanho]
        pts = int(b["pontos"].sum())
        saida.append({
            "rotulo": f"Jogos {i + 1} a {i + len(b)}",
            "pontos": pts, "disputados": 3 * len(b), "aproveitamento": _pct(pts, 3 * len(b)),
        })
    return saida


# ----------------------------------------------------------------------------
# Classificação e evolução
# ----------------------------------------------------------------------------
def tabela_ate(df: pd.DataFrame, rodada: int) -> pd.DataFrame:
    """Classificação calculada com os jogos encerrados até a rodada informada.
    Critérios: pontos, vitórias, saldo, gols pró (confronto direto e cartões não
    entram, então empates perfeitos nesses 4 critérios podem divergir da oficial)."""
    j = df[df["encerrado"] & (df["rodada"] <= rodada)]
    casa = pd.DataFrame({"time": j["mandante_id"], "gp": j["gm"], "gc": j["gv"]})
    fora = pd.DataFrame({"time": j["visitante_id"], "gp": j["gv"], "gc": j["gm"]})
    x = pd.concat([casa, fora])
    x["v"] = (x["gp"] > x["gc"]).astype(int)
    x["e"] = (x["gp"] == x["gc"]).astype(int)
    t = x.groupby("time").agg(v=("v", "sum"), e=("e", "sum"), gp=("gp", "sum"), gc=("gc", "sum"), j=("v", "size"))
    todos = pd.Index(pd.concat([df["mandante_id"], df["visitante_id"]]).unique(), name="time")
    t = t.reindex(todos, fill_value=0)
    t["pts"] = 3 * t["v"] + t["e"]
    t["sg"] = t["gp"] - t["gc"]
    t = t.sort_values(["pts", "v", "sg", "gp"], ascending=False)
    t["pos"] = range(1, len(t) + 1)
    return t


def evolucao(df: pd.DataFrame, time_id: int) -> list[dict]:
    rodadas = sorted(int(r) for r in df.loc[df["encerrado"], "rodada"].dropna().unique())
    saida = []
    for r in rodadas:
        t = tabela_ate(df, r)
        saida.append({
            "rodada": r,
            "posicao": int(t.loc[time_id, "pos"]),
            "pontos": int(t.loc[time_id, "pts"]),
            "jogos": int(t.loc[time_id, "j"]),
            "pontos_lider": int(t["pts"].iloc[0]),
            "pontos_g4": int(t["pts"].iloc[3]),
            "pontos_z4": int(t["pts"].iloc[16]),  # 17º colocado
        })
    return saida


def tabela_oficial(standings: dict, time_id: int) -> list[dict]:
    total = next((s for s in standings.get("standings", []) if s.get("type") == "TOTAL"), None)
    if not total:
        return []
    return [
        {
            "posicao": l["position"],
            "time": l["team"].get("shortName") or l["team"]["name"],
            "escudo": l["team"].get("crest"),
            "destaque": l["team"]["id"] == time_id,
            "jogos": l["playedGames"], "vitorias": l["won"], "empates": l["draw"],
            "derrotas": l["lost"], "pontos": l["points"],
            "gols_pro": l["goalsFor"], "gols_contra": l["goalsAgainst"], "saldo": l["goalDifference"],
        }
        for l in total["table"]
    ]


# ----------------------------------------------------------------------------
# Simulação do restante do campeonato (Monte Carlo com gols de Poisson)
# ----------------------------------------------------------------------------
def simular(df: pd.DataFrame, time_id: int) -> dict | None:
    """Força de ataque e defesa de cada time, separada por mando, estimada pelos
    gols dos jogos encerrados e puxada para a média da liga (ENCOLHIMENTO).
    Cada jogo restante vira dois sorteios de Poisson. Semente fixa derivada dos
    dados: mesma entrada, mesmo resultado."""
    enc = df[df["encerrado"]]
    rest = df[~df["encerrado"] & ~df["status"].isin(CANCELADO)]
    if enc.empty or rest.empty:
        return None

    times = pd.Index(pd.concat([df["mandante_id"], df["visitante_id"]]).unique())
    idx = {t: i for i, t in enumerate(times)}
    mu_casa, mu_fora = enc["gm"].mean(), enc["gv"].mean()

    def forca(grupo: str, gols: str, media: float) -> pd.Series:
        g = enc.groupby(grupo)[gols].agg(["sum", "count"]).reindex(times, fill_value=0)
        return ((g["sum"] + ENCOLHIMENTO * media) / (g["count"] + ENCOLHIMENTO)) / media

    ataque_casa = forca("mandante_id", "gm", mu_casa)
    defesa_casa = forca("mandante_id", "gv", mu_fora)   # gols sofridos em casa
    ataque_fora = forca("visitante_id", "gv", mu_fora)
    defesa_fora = forca("visitante_id", "gm", mu_casa)  # gols sofridos fora

    h = rest["mandante_id"].map(idx).to_numpy()
    a = rest["visitante_id"].map(idx).to_numpy()
    lam_h = mu_casa * ataque_casa.loc[rest["mandante_id"]].to_numpy() * defesa_fora.loc[rest["visitante_id"]].to_numpy()
    lam_a = mu_fora * ataque_fora.loc[rest["visitante_id"]].to_numpy() * defesa_casa.loc[rest["mandante_id"]].to_numpy()

    base = tabela_ate(df, RODADAS).reindex(times)
    rng = np.random.default_rng(len(enc) * 1000 + int(enc["gm"].sum() + enc["gv"].sum()))
    gh = rng.poisson(lam_h, size=(N_SIMULACOES, len(rest)))
    ga = rng.poisson(lam_a, size=(N_SIMULACOES, len(rest)))

    n_t = len(times)
    pts = np.tile(base["pts"].to_numpy(float), (N_SIMULACOES, 1))
    vit = np.tile(base["v"].to_numpy(float), (N_SIMULACOES, 1))
    sg = np.tile(base["sg"].to_numpy(float), (N_SIMULACOES, 1))
    gp = np.tile(base["gp"].to_numpy(float), (N_SIMULACOES, 1))
    ph = np.where(gh > ga, 3, np.where(gh == ga, 1, 0))
    pa = np.where(ga > gh, 3, np.where(gh == ga, 1, 0))
    for k in range(len(rest)):
        pts[:, h[k]] += ph[:, k]
        pts[:, a[k]] += pa[:, k]
        vit[:, h[k]] += gh[:, k] > ga[:, k]
        vit[:, a[k]] += ga[:, k] > gh[:, k]
        sg[:, h[k]] += gh[:, k] - ga[:, k]
        sg[:, a[k]] += ga[:, k] - gh[:, k]
        gp[:, h[k]] += gh[:, k]
        gp[:, a[k]] += ga[:, k]

    chave = pts * 1e9 + vit * 1e6 + (sg + 500) * 1e3 + gp + rng.random((N_SIMULACOES, n_t))
    ordem = np.argsort(-chave, axis=1)
    posicao = np.empty_like(ordem)
    np.put_along_axis(posicao, ordem, np.arange(1, n_t + 1)[None, :].repeat(N_SIMULACOES, 0), axis=1)

    i = idx[time_id]
    pos_t = posicao[:, i]
    pts_t = pts[:, i].astype(int)
    dist = np.bincount(pos_t, minlength=n_t + 1)[1:] / N_SIMULACOES
    valores, contagem = np.unique(pts_t, return_counts=True)
    p25, p50, p75 = np.percentile(pts_t, [25, 50, 75])

    return {
        "simulacoes": N_SIMULACOES,
        "jogos_restantes_liga": int(len(rest)),
        "prob": {
            "titulo": round(100 * float((pos_t == 1).mean()), 1),
            "g4": round(100 * float((pos_t <= 4).mean()), 1),
            "g6": round(100 * float((pos_t <= 6).mean()), 1),
            "sul_americana": round(100 * float(((pos_t >= 7) & (pos_t <= 12)).mean()), 1),
            "z4": round(100 * float((pos_t >= 17).mean()), 1),
        },
        "pontos": {
            "p25": int(p25), "mediana": int(p50), "p75": int(p75),
            "min": int(pts_t.min()), "max": int(pts_t.max()),
            "mais_provavel": int(valores[contagem.argmax()]),
        },
        "posicao_mais_provavel": int(dist.argmax() + 1),
        "distribuicao_posicao": [round(100 * float(x), 2) for x in dist],
    }


# ----------------------------------------------------------------------------
# Listas para o front
# ----------------------------------------------------------------------------
def _num(x):
    return None if pd.isna(x) else int(x)


def lista_jogos(t: pd.DataFrame) -> list[dict]:
    acumulado = t["pontos"].fillna(0).cumsum()
    return [
        {
            "rodada": _num(r["rodada"]),
            "data": r["data"].isoformat(),
            "status": r["status"],
            "mando": r["mando"],
            "adversario": r["adversario"],
            "adversario_escudo": r["adversario_escudo"],
            "gp": _num(r["gp"]), "gc": _num(r["gc"]),
            "gp_int": _num(r["gp_int"]), "gc_int": _num(r["gc_int"]),
            "resultado": r["resultado"] if isinstance(r["resultado"], str) else None,
            "pontos": _num(r["pontos"]),
            "acumulado": int(ac) if r["encerrado"] else None,
        }
        for (_, r), ac in zip(t.iterrows(), acumulado)
    ]


# ----------------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------------
def montar(jogos_api: dict, standings: dict) -> dict:
    df = jogos_para_dataframe(jogos_api["matches"])
    time_id, time_nome = achar_time(df)
    t = visao_do_time(df, time_id)
    enc = t[t["encerrado"]]
    futuros = t[~t["encerrado"] & ~t["status"].isin(CANCELADO)]

    tabela = tabela_oficial(standings, time_id)
    linha = next((l for l in tabela if l["destaque"]), None)
    escudo = next((e for e in t["mandante_escudo"].where(t["mando"] == "casa").dropna()), None)

    return {
        "fonte": "football-data.org",
        "temporada": TEMPORADA,
        "competicao": "Brasileirão Série A",
        "time": {"id": time_id, "nome": time_nome, "escudo": escudo},
        "rodada_atual": int(df.loc[df["encerrado"], "rodada"].max()) if df["encerrado"].any() else None,
        "posicao": linha["posicao"] if linha else None,
        "jogos_restantes": int(len(futuros)),
        "periodo": {
            "inicio": enc["data"].min().isoformat() if len(enc) else None,
            "fim": enc["data"].max().isoformat() if len(enc) else None,
        },
        "recortes": {
            "todos": recorte(enc),
            "casa": recorte(enc[enc["mando"] == "casa"]),
            "fora": recorte(enc[enc["mando"] == "fora"]),
        },
        "blocos": blocos(enc),
        "evolucao": evolucao(df, time_id),
        "simulacao": simular(df, time_id),
        "proximos": lista_jogos(futuros)[:10],
        "jogos": lista_jogos(t),
        "tabela": tabela,
    }


def salvar_se_mudou(dados: dict) -> bool:
    anterior = None
    if SAIDA.exists():
        anterior = json.loads(SAIDA.read_text(encoding="utf-8"))
        anterior.pop("atualizado_em", None)
    if anterior == json.loads(json.dumps(dados, ensure_ascii=False)):
        return False
    dados = {"atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), **dados}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def main() -> int:
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        print("ERRO: FOOTBALL_DATA_TOKEN não definido", file=sys.stderr)
        return 1
    jogos_api = buscar(f"/competitions/{COMPETICAO}/matches", token)
    standings = buscar(f"/competitions/{COMPETICAO}/standings", token)
    dados = montar(jogos_api, standings)
    r = dados["recortes"]["todos"]["resumo"]
    print(f"{dados['time']['nome']}: {dados['posicao']}º, {r['pontos']} pts em {r['jogos']} jogos "
          f"({r['vitorias']}V {r['empates']}E {r['derrotas']}D), rodada {dados['rodada_atual']}")
    if dados["simulacao"]:
        print(f"Simulação: {dados['simulacao']['prob']}")
    print("data/dashboard.json atualizado" if salvar_se_mudou(dados) else "Sem mudanças nos dados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
