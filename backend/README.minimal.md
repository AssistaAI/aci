# Docker Compose Minimal - Ghid de utilizare

## Pornire configurație minimală

```bash
docker-compose -f compose.minimal.yml up --build
```

## Ce servicii rulează?

✅ **Servicii active** (pornesc automat):
- `db` - PostgreSQL cu pgvector (limitat la 512MB RAM, 1 CPU)
- `aws` - LocalStack pentru KMS (limitat la 512MB RAM, 0.5 CPU)
- `propelauth_mock` - Mock auth server (limitat la 256MB RAM, 0.5 CPU)
- `server` - FastAPI backend (limitat la 1GB RAM, 1 CPU)

❌ **Servicii ELIMINATE** (economisesc ~1.5-2GB RAM):
- `test-db` - Pornește doar când rulezi teste
- `test-runner` - Pornește doar când rulezi teste
- `runner` - Pornește doar când ai nevoie de CLI

## Optimizări aplicate

1. **Limite de resurse** - fiecare container are limite clare de RAM și CPU
2. **Debug dezactivat** - LocalStack rulează cu logging minimal
3. **Healthcheck-uri mai rare** - verificări la fiecare 30s în loc de 10s
4. **Runner nu mai rulează permanent** - pornește doar la cerere
5. **PostgreSQL optimizat** - shared memory limitat la 128MB

## Total consum resurse estimate

- **RAM**: ~2.5GB (vs ~4-5GB în configurația completă)
- **CPU**: ~3 cores (vs ~6-8 cores)

## Cum pornești runner-ul când ai nevoie

### Pentru migrații DB:
```bash
docker-compose -f compose.minimal.yml run --rm runner alembic upgrade head
```

### Pentru seed DB:
```bash
docker-compose -f compose.minimal.yml run --rm runner ./scripts/seed_db.sh
```

### Pentru CLI:
```bash
docker-compose -f compose.minimal.yml run --rm runner python -m aci.cli --help
docker-compose -f compose.minimal.yml run --rm runner python -m aci.cli upsert-app --app-file ./apps/gmail/app.json
```

### Pentru shell interactiv:
```bash
docker-compose -f compose.minimal.yml run --rm runner /bin/bash
```

## Cum rulezi testele (când ai nevoie)

Configurația minimală NU include test-db și test-runner. Când vrei să rulezi teste:

```bash
# Pornește test-db separat
docker-compose -f compose.yml up test-db -d

# Rulează testele
docker-compose -f compose.yml run --rm test-runner pytest
```

## Oprire

```bash
docker-compose -f compose.minimal.yml down
```

## Când folosești compose.yml complet?

Folosește `compose.yml` original când:
- Rulezi teste intensive
- Dezvolți functionalități care necesită runner activ permanent
- Ai nevoie de debugging avansat pe LocalStack

## Troubleshooting

### Server nu pornește / unhealthy
```bash
docker-compose -f compose.minimal.yml logs server
```

### Database connection failed
Asigură-te că migrațiile sunt aplicate:
```bash
docker-compose -f compose.minimal.yml run --rm runner alembic upgrade head
```

### LocalStack KMS errors
Verifică că scriptul de inițializare a rulat:
```bash
docker-compose -f compose.minimal.yml logs aws
```
