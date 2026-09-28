"""
Diagnóstico das APIs de futebol (plano gratuito) para o Brasileirão Série A 2026.

Testa duas fontes:
  1. football-data.org (v4)       -> variável de ambiente FOOTBALL_DATA_TOKEN
  2. API-Football (api-sports.io) -> variável de ambiente API_FOOTBALL_KEY

Para cada uma, responde:
  a) a temporada 2026 está liberada no plano atual?
  b) há minuto dos gols e placar do intervalo?
  c) qual o limite de requisições (lido dos headers / endpoint de status)?
  d) quantas chamadas seriam necessárias para coletar todos os jogos?

Uso:
  export FOOTBALL_DATA_TOKEN="..."
  export API_FOOTBALL_KEY="..."
  python scripts/diagnostico_apis.py [--saida diagnostico.json]

Consumo estimado do próprio diagnóstico:
  football-data.org: 3 requisições
  API-Football: 3 requisições contadas na cota diária (/status não conta)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import requests

TEMPORADA = 2026
TIMEOUT = 30

FD_BASE = "https://api.football-data.org/v4"
FD_COMPETICAO = "BSA"  # Campeonato Brasileiro Série A

AF_BASE = "https://v3.football.api-sports.io"
AF_LIGA = 71  # Serie A (Brasil)
AF_MAX_IDS_POR_CHAMADA = 20  # limite do parâmetro ids= em /fixtures

# Status que indicam jogo encerrado em cada API
FD_ENCERRADO = {"FINISHED", "AWARDED"}
AF_ENCERRADO = {"FT", "AET", "PEN", "AWD", "WO"}


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def get(url: str, headers: dict, params: dict | None = None) -> tuple[int, dict, dict | None, str]:
    """Faz GET e devolve (status, headers, json|None, texto_erro)."""
    try:
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return 0, {}, None, f"falha de rede: {exc}"
    try:
        corpo = r.json()
    except ValueError:
        corpo = None
    return r.status_code, dict(r.headers), corpo, r.text[:300] if corpo is None else ""


def headers_limite(h: dict, prefixos: tuple[str, ...]) -> dict:
    """Filtra os headers relacionados a limite de requisições."""
    return {k: v for k, v in h.items() if k.lower().startswith(prefixos)}


def linha(txt: str = "") -> None:
    print(txt)


# ----------------------------------------------------------------------------
# football-data.org
# ----------------------------------------------------------------------------
def diagnosticar_football_data(token: str | None) -> dict:
    res: dict = {"api": "football-data.org", "chave_presente": bool(token)}
    if not token:
        res["erro"] = "FOOTBALL_DATA_TOKEN não definido"
        return res

    h = {"X-Auth-Token": token}

    # 1) Competição: temporada corrente e plano
    st, hd, js, err = get(f"{FD_BASE}/competitions/{FD_COMPETICAO}", h)
    res["competicao_status_http"] = st
    res["limite_headers"] = headers_limite(hd, ("x-requests", "x-requestcounter", "x-authenticated"))
    if st != 200 or not js:
        res["erro"] = (js or {}).get("message") or err or f"HTTP {st}"
        return res
    cs = js.get("currentSeason") or {}
    res["temporada_corrente"] = {
        "inicio": cs.get("startDate"),
        "fim": cs.get("endDate"),
        "rodada_atual": cs.get("currentMatchday"),
    }

    # 2) Lista de jogos da temporada 2026 (uma única chamada traz todos)
    st, hd, js, err = get(
        f"{FD_BASE}/competitions/{FD_COMPETICAO}/matches", h, {"season": TEMPORADA}
    )
    res["jogos_status_http"] = st
    res["limite_headers"] = headers_limite(hd, ("x-requests", "x-requestcounter", "x-authenticated")) or res["limite_headers"]
    if st != 200 or not js:
        res["temporada_liberada"] = False
        res["erro"] = (js or {}).get("message") or err or f"HTTP {st}"
        return res

    jogos = js.get("matches", [])
    encerrados = [m for m in jogos if m.get("status") in FD_ENCERRADO]
    res["temporada_liberada"] = len(jogos) > 0
    res["total_jogos"] = len(jogos)
    res["jogos_encerrados"] = len(encerrados)
    res["times"] = len({m["homeTeam"]["id"] for m in jogos} | {m["awayTeam"]["id"] for m in jogos})

    com_intervalo = [
        m for m in encerrados
        if (m.get("score") or {}).get("halfTime", {}).get("home") is not None
    ]
    res["placar_intervalo"] = {
        "disponivel": len(com_intervalo) > 0,
        "jogos_encerrados_com_intervalo": f"{len(com_intervalo)}/{len(encerrados)}",
    }
    res["gols_na_listagem"] = any(m.get("goals") for m in encerrados)

    # 3) Detalhe de 1 jogo encerrado: verifica se vem lista de gols com minuto
    minuto = {"disponivel": False, "fonte": None, "amostra": None}
    if encerrados:
        alvo = next(
            (m for m in reversed(encerrados)
             if (m["score"]["fullTime"]["home"] or 0) + (m["score"]["fullTime"]["away"] or 0) > 0),
            encerrados[-1],
        )
        st, hd, js, err = get(f"{FD_BASE}/matches/{alvo['id']}", h)
        res["detalhe_status_http"] = st
        res["limite_headers"] = headers_limite(hd, ("x-requests", "x-requestcounter", "x-authenticated")) or res["limite_headers"]
        if st == 200 and js:
            gols = js.get("goals")
            minuto["chave_goals_presente"] = "goals" in js
            if gols:
                minuto.update(
                    disponivel=all(g.get("minute") is not None for g in gols),
                    fonte="GET /v4/matches/{id} -> goals[].minute",
                    amostra=[
                        {"minuto": g.get("minute"), "acrescimo": g.get("injuryTime"),
                         "time": (g.get("team") or {}).get("name"),
                         "autor": (g.get("scorer") or {}).get("name")}
                        for g in gols[:3]
                    ],
                )
            minuto["jogo_testado"] = (
                f"{alvo['homeTeam']['name']} {alvo['score']['fullTime']['home']} x "
                f"{alvo['score']['fullTime']['away']} {alvo['awayTeam']['name']}"
            )
        else:
            minuto["erro"] = (js or {}).get("message") or err or f"HTTP {st}"
    res["minuto_gols"] = minuto

    # 4) Estimativa de chamadas para coleta completa
    por_minuto = _int(res["limite_headers"], "x-requests-available-minute")
    n_detalhe = len(encerrados) if minuto["disponivel"] else 0
    total = 1 + n_detalhe
    res["estimativa_chamadas"] = {
        "listagem_todos_os_jogos": 1,
        "detalhe_por_jogo_para_minuto_dos_gols": n_detalhe,
        "total_carga_inicial": total,
        "total_se_temporada_completa_380_jogos": 1 + (380 if minuto["disponivel"] else 0),
        "atualizacao_incremental_por_rodada": 1 + (10 if minuto["disponivel"] else 0),
        "observacao": (
            "Limite do plano gratuito é por minuto (não há cota diária). "
            "Tempo mínimo da carga inicial a 10 req/min: "
            f"~{math.ceil(total / 10)} min."
        ),
        "restantes_no_minuto_agora": por_minuto,
    }
    return res


# ----------------------------------------------------------------------------
# API-Football (api-sports.io)
# ----------------------------------------------------------------------------
def diagnosticar_api_football(chave: str | None) -> dict:
    res: dict = {"api": "API-Football (api-sports.io)", "chave_presente": bool(chave)}
    if not chave:
        res["erro"] = "API_FOOTBALL_KEY não definido"
        return res

    h = {"x-apisports-key": chave}
    prefixos = ("x-ratelimit",)

    # 1) Status da conta (não consome cota)
    st, hd, js, err = get(f"{AF_BASE}/status", h)
    res["status_http"] = st
    if st != 200 or not js:
        res["erro"] = err or f"HTTP {st}"
        return res
    if js.get("errors"):
        res["erro"] = js["errors"]
        return res
    conta = js.get("response") or {}
    res["plano"] = (conta.get("subscription") or {}).get("plan")
    res["cota_diaria"] = conta.get("requests")  # {"current": x, "limit_day": y}

    # 2) Liga + cobertura declarada para 2026
    st, hd, js, err = get(f"{AF_BASE}/leagues", h, {"id": AF_LIGA})
    res["limite_headers"] = headers_limite(hd, prefixos)
    temporadas = []
    cobertura_2026 = None
    if st == 200 and js and js.get("response"):
        temporadas = [s["year"] for s in js["response"][0].get("seasons", [])]
        for s in js["response"][0].get("seasons", []):
            if s["year"] == TEMPORADA:
                cobertura_2026 = {
                    "inicio": s.get("start"),
                    "fim": s.get("end"),
                    "atual": s.get("current"),
                    "fixtures": (s.get("coverage") or {}).get("fixtures"),
                }
    res["temporadas_catalogadas"] = temporadas[-6:]
    res["cobertura_declarada_2026"] = cobertura_2026
    if js and js.get("errors"):
        res["erro_leagues"] = js["errors"]

    # 3) Jogos da temporada 2026 (uma chamada traz todos)
    st, hd, js, err = get(f"{AF_BASE}/fixtures", h, {"league": AF_LIGA, "season": TEMPORADA})
    res["limite_headers"] = headers_limite(hd, prefixos) or res.get("limite_headers")
    erros = (js or {}).get("errors")
    if st != 200 or not js or erros:
        res["temporada_liberada"] = False
        res["erro_fixtures"] = erros or err or f"HTTP {st}"
        res["estimativa_chamadas"] = _estimativa_af(0, liberada=False)
        return res

    jogos = js.get("response", [])
    encerrados = [f for f in jogos if f["fixture"]["status"]["short"] in AF_ENCERRADO]
    res["temporada_liberada"] = len(jogos) > 0
    res["total_jogos"] = len(jogos)
    res["jogos_encerrados"] = len(encerrados)
    res["times"] = len({f["teams"]["home"]["id"] for f in jogos} | {f["teams"]["away"]["id"] for f in jogos})

    com_intervalo = [f for f in encerrados if (f.get("score") or {}).get("halftime", {}).get("home") is not None]
    res["placar_intervalo"] = {
        "disponivel": len(com_intervalo) > 0,
        "jogos_encerrados_com_intervalo": f"{len(com_intervalo)}/{len(encerrados)}",
    }

    # 4) Minuto dos gols: /fixtures?ids= (até 20 jogos por chamada, já com eventos)
    minuto = {"disponivel": False, "fonte": None, "amostra": None}
    if encerrados:
        lote = [str(f["fixture"]["id"]) for f in encerrados[-AF_MAX_IDS_POR_CHAMADA:]]
        st, hd, js, err = get(f"{AF_BASE}/fixtures", h, {"ids": "-".join(lote)})
        res["limite_headers"] = headers_limite(hd, prefixos) or res.get("limite_headers")
        if st == 200 and js and not js.get("errors"):
            gols = [
                {"minuto": e["time"]["elapsed"], "acrescimo": e["time"].get("extra"),
                 "time": e["team"]["name"], "autor": (e.get("player") or {}).get("name"),
                 "tipo": e.get("detail")}
                for f in js.get("response", []) for e in (f.get("events") or [])
                if e.get("type") == "Goal"
            ]
            if gols:
                minuto.update(
                    disponivel=all(g["minuto"] is not None for g in gols),
                    fonte=f"GET /fixtures?ids=... (até {AF_MAX_IDS_POR_CHAMADA} jogos) -> events[type=Goal].time",
                    amostra=gols[:3],
                    gols_no_lote=len(gols),
                )
        else:
            minuto["erro"] = (js or {}).get("errors") or err or f"HTTP {st}"
    res["minuto_gols"] = minuto
    res["estimativa_chamadas"] = _estimativa_af(len(encerrados), liberada=True)
    return res


def _estimativa_af(n_encerrados: int, liberada: bool) -> dict:
    lotes = math.ceil(n_encerrados / AF_MAX_IDS_POR_CHAMADA)
    return {
        "listagem_todos_os_jogos": 1,
        "eventos_em_lotes_de_20": lotes,
        "total_carga_inicial": 1 + lotes,
        "total_se_temporada_completa_380_jogos": 1 + math.ceil(380 / AF_MAX_IDS_POR_CHAMADA),
        "alternativa_sem_lote_/fixtures/events": 1 + 380,
        "atualizacao_incremental_por_rodada": 2,
        "observacao": (
            "Valores teóricos; só são aplicáveis se a temporada estiver liberada."
            if not liberada else
            "Plano gratuito tem cota diária (ver cota_diaria) e limite por minuto (ver limite_headers)."
        ),
    }


def _int(d: dict, chave: str) -> int | None:
    for k, v in d.items():
        if k.lower() == chave:
            try:
                return int(v)
            except ValueError:
                return None
    return None


# ----------------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------------
def resumo(r: dict) -> None:
    linha("=" * 72)
    linha(r["api"])
    linha("=" * 72)
    if r.get("erro"):
        linha(f"  ERRO: {r['erro']}")
    sim_nao = lambda v: "SIM" if v else ("NÃO" if v is not None else "indeterminado")
    linha(f"  Temporada {TEMPORADA} liberada ........ {sim_nao(r.get('temporada_liberada'))}")
    if r.get("erro_fixtures"):
        linha(f"    motivo: {r['erro_fixtures']}")
    if "total_jogos" in r:
        linha(f"    jogos: {r['total_jogos']} | encerrados: {r['jogos_encerrados']} | times: {r['times']}")
    pi = r.get("placar_intervalo") or {}
    linha(f"  Placar do intervalo ............. {sim_nao(pi.get('disponivel'))} {pi.get('jogos_encerrados_com_intervalo', '')}")
    mg = r.get("minuto_gols") or {}
    linha(f"  Minuto dos gols ................. {sim_nao(mg.get('disponivel')) if 'minuto_gols' in r else 'indeterminado'}")
    if mg.get("fonte"):
        linha(f"    fonte: {mg['fonte']}")
    if mg.get("amostra"):
        linha(f"    amostra: {mg['amostra']}")
    if mg.get("erro"):
        linha(f"    erro: {mg['erro']}")
    linha("  Limite de requisições:")
    if r.get("plano"):
        linha(f"    plano: {r['plano']} | cota diária: {r.get('cota_diaria')}")
    for k, v in (r.get("limite_headers") or {}).items():
        linha(f"    {k}: {v}")
    est = r.get("estimativa_chamadas")
    if est:
        linha("  Chamadas para coleta completa:")
        for k, v in est.items():
            linha(f"    {k}: {v}")
    linha()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", help="caminho opcional para salvar o resultado em JSON")
    args = ap.parse_args()

    resultados = [
        diagnosticar_football_data(os.getenv("FOOTBALL_DATA_TOKEN")),
        diagnosticar_api_football(os.getenv("API_FOOTBALL_KEY")),
    ]
    linha(f"Diagnóstico executado em {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    linha(f"Temporada alvo: Brasileirão Série A {TEMPORADA}\n")
    for r in resultados:
        resumo(r)

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)
        linha(f"Resultado salvo em {args.saida}")

    return 0 if all(r.get("chave_presente") for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
