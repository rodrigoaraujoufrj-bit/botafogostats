# botafogostats

Dashboard da campanha do Botafogo no Brasileirão Série A 2026, publicado via GitHub Pages
e atualizado automaticamente por GitHub Actions.

## Como funciona

```
football-data.org ──(GitHub Actions, a cada 2 h)──> scripts/coletar.py ──> data/dashboard.json ──> index.html
```

| Parte | Arquivo | O que faz |
|---|---|---|
| Coleta e métricas | `scripts/coletar.py` | 2 requisições por execução (jogos + classificação); calcula as métricas com pandas e simula o restante do campeonato |
| Dados | `data/dashboard.json` | JSON estático lido pelo site; só é reescrito quando os dados mudam |
| Site | `index.html`, `assets/` | HTML/CSS/JS puro com Chart.js, responsivo, modo claro e escuro |
| Atualização | `.github/workflows/atualizar.yml` | roda a coleta a cada 2 horas e faz commit dos dados novos |
| Diagnóstico | `scripts/diagnostico_apis.py` | teste das APIs usado na etapa 1 (execução manual) |

## Fonte de dados

football-data.org, plano gratuito: temporada 2026 liberada, placar final e do intervalo,
10 requisições por minuto. O plano gratuito **não** traz o minuto dos gols, por isso o
painel trabalha com 1º e 2º tempo (2º tempo = placar final menos placar do intervalo).

## Métricas

- Aproveitamento, campanha (V/E/D), média de pontos e saldo, com filtro todos / casa / fora
- Posição e pontos rodada a rodada, comparados ao líder, ao 4º e ao 17º colocado
- Mando de campo, sequências, rendimento por blocos de 10 jogos
- Antes e depois do intervalo: gols por tempo, viradas e pontos ganhos ou perdidos no 2º tempo
- Cenários: probabilidades de título, G4, top 6 e rebaixamento

### Como os cenários são calculados

Simulação de Monte Carlo (20 mil repetições) dos jogos restantes de **todo** o campeonato.
A força de ataque e de defesa de cada time, separada por mando, vem dos gols dos jogos
encerrados, puxada para a média da liga para não exagerar amostras pequenas. Cada jogo vira
dois sorteios de Poisson. Limitações: não considera desfalques, mudança de técnico nem
calendário de outras competições; o desempate usa pontos, vitórias, saldo e gols pró.
São estimativas, não previsões garantidas.

## Configuração

1. **Secret:** `Settings > Secrets and variables > Actions` com `FOOTBALL_DATA_TOKEN`.
2. **Pages:** `Settings > Pages > Build and deployment > Deploy from a branch`, branch `main`, pasta `/ (root)`.
3. **Primeira carga:** aba `Actions > Atualizar dados > Run workflow`.

## Rodar localmente

```bash
pip install -r requirements.txt
export FOOTBALL_DATA_TOKEN="sua_chave"
python scripts/coletar.py
python -m http.server 8000   # abra http://localhost:8000
```
