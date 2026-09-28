# botafogostats

Dashboard da campanha do Botafogo no Brasileirão Série A 2026.

## Etapa 1: diagnóstico das APIs

Antes de escrever a coleta, o script `scripts/diagnostico_apis.py` testa as duas
fontes candidatas no plano gratuito:

| Fonte | Variável de ambiente | Cadastro |
|---|---|---|
| football-data.org (v4) | `FOOTBALL_DATA_TOKEN` | https://www.football-data.org/client/register |
| API-Football (api-sports.io) | `API_FOOTBALL_KEY` | https://dashboard.api-football.com/register |

Para cada uma, o script informa:

- se a temporada 2026 está liberada no plano atual;
- se há placar do intervalo e minuto dos gols;
- o limite de requisições (lido dos headers da resposta e, na API-Football, do endpoint `/status`);
- quantas chamadas seriam necessárias para a carga completa e para a atualização por rodada.

### Como rodar

```bash
pip install -r requirements.txt
export FOOTBALL_DATA_TOKEN="sua_chave"
export API_FOOTBALL_KEY="sua_chave"
python scripts/diagnostico_apis.py --saida diagnostico.json
```

Consumo do próprio diagnóstico: 3 requisições na football-data.org e 3 na
API-Football (o `/status` não conta na cota diária).
