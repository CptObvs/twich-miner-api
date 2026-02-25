# Twitch Miner Backend

FastAPI-Backend als Multi-User-Orchestrator für [TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner) und [TwitchChannelPointsMiner V2](https://github.com/rdavidoff/Twitch-Channel-Points-Miner-v2). Beide Miner laufen als Docker-Container, verwaltet pro User über eine REST-API mit JWT-Authentifizierung.

**Frontend:** [twitch-miner-frontend](https://github.com/CptObvs/twitch-miner-frontend)

## Miner-Typen

| Typ | Beschreibung |
|-----|-------------|
| **TwitchDropsMiner** | Drop-Farming mit Web-UI, erreichbar via Backend-Proxy |
| **TwitchChannelPointsMiner V2** | Channel-Points-Farming, Logs persistent in `output.log` |

Docker-Images werden über `.env` konfiguriert (`DOCKER_IMAGE`, `V2_DOCKER_IMAGE`).
