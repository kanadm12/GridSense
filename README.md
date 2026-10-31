# GridSense

**Grid-Aware Energy Copilot for Victorian Households**

GridSense is a prototype for reviewing smart-meter data, estimating energy costs, and previewing flexible-load schedules for Australian households. It includes a FastAPI backend and an Expo/React Native client.

> **Prototype status:** GridSense is not a production energy service. Demo accounts, readings, and time-of-use prices are synthetic. NEM12 parsing does not by itself establish register direction or validate a retailer bill, and scheduling recommendations are previews only; they do not control appliances.

## Features

- **NEM12 import** - Upload and parse interval-data files, with data-quality and unresolved-channel-direction handling.
- **Usage analytics** - Review daily and interval consumption where the reading direction is known.
- **Tariffs and billing estimates** - Configure tariffs and compare estimated energy charges; estimates may be partial when data are incomplete.
- **Recommendations** - View rule-based energy-use suggestions.
- **Scheduling preview** - Compare a synthetic flexible-load schedule with a deterministic reference under configured time-of-use rates. The result is advisory and does not dispatch a device.
- **Additional prototype surfaces** - Forecasting, notifications, AI assistance, and home-automation interfaces are present; external-service and production operation require separate configuration and verification.

## Demonstration and verification

The current demonstration uses two separate synthetic accounts: one for analytics and one for time-of-use scheduling. The imported NEM12 parser fixture is separate from the seeded analytics readings.

- [Demo runbook](backend/docs/demo/DEMO_RUNBOOK.md)
- [Final demo acceptance report](backend/docs/demo/FINAL_DEMO_ACCEPTANCE.md) — **PARTIAL**: the browser interactions and screenshots were verified, but a timed uninterrupted walkthrough and screen recording remain outstanding.
- [Screenshots and evidence guide](backend/docs/demo/SCREENSHOTS.md)
- [Claim-evidence matrix](backend/docs/demo/CLAIM_EVIDENCE_MATRIX.md)
- [Product one-pager](backend/docs/demo/PRODUCT_ONE_PAGER.md)
- [Development status](DEVELOPMENT_STATUS.md)
- [Baseline and verification log](BASELINE_VERIFICATION.md)
- [Detailed implementation history](GridSense_Detailed_Implementation_Prompts.md)

Latest recorded checks: backend tests **189 passed** with 11 warnings; mobile TypeScript passed. Full Ruff reported 226 findings, and mobile lint/tests could not run because `eslint` and `jest` were unavailable. PostgreSQL/Redis runtime and restore verification were not performed. See the acceptance report for exact environment, commands, results, and limitations.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │
│   Mobile App    │────▶│   FastAPI       │
│   (React Native)│     │   Backend       │
│                 │     │                 │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   PostgreSQL    │
                        │   Database      │
                        └─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+
- Docker (optional)

### Using Docker Compose (Recommended)

When Docker Desktop's Linux engine is available:

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f api
```

API available at: http://localhost:8000/docs

### Manual Setup

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Set up environment
cp .env.example .env

# Start PostgreSQL (Docker)
docker run -d --name gridsense-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=gridsense -p 5432:5432 postgres:16

# Run server
uvicorn app.main:app --reload
```

#### Mobile App

```bash
cd mobile

# Install dependencies
npm install

# Start Expo
npx expo start
```

## Project Structure

```
GridSense/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/             # API routes
│   │   ├── models/          # Database models
│   │   ├── schemas/         # Pydantic schemas
│   │   └── services/        # Business logic
│   └── tests/
├── mobile/                  # React Native app
│   ├── app/                 # Expo Router screens
│   ├── components/
│   ├── services/            # API client
│   └── stores/              # Zustand stores
└── docker-compose.yml
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get access token |
| POST | `/api/v1/upload` | Upload NEM12 file |
| GET | `/api/v1/meters` | List user's meters |
| GET | `/api/v1/usage/summary/{meter_id}` | Usage summary |
| GET | `/api/v1/usage/daily/{meter_id}` | Daily breakdown |
| GET | `/api/v1/usage/hourly/{meter_id}` | Hourly pattern |
| GET | `/api/v1/recommendations/{meter_id}` | Get recommendations |

## NEM12 Format

NEM12 is the Australian standard for smart meter interval data. Sample structure:

```csv
100,NEM12,200506081149,UNITEDDP,NEMMCO
200,VAAA000000,E1,E1,E1,N1,01009,kWh,30,
300,20050301,0.0,0.0,0.1,0.2,...,A,,,20050310121004,
...
900
```

Get your NEM12 file from:
- Your energy retailer's online portal
- Request from your distribution network (AusNet, United Energy, etc.)

## Development status

- **Core prototype:** authentication, meter and upload flows, analytics, configured-tariff estimates, and rule-based recommendations are implemented.
- **Scheduling:** an advisory scheduling preview and synthetic time-of-use demonstration are implemented; live device control and a consumption-derived scheduling baseline are not established.
- **Research and forecasting:** evaluation tooling and synthetic scheduling experiments are included; their results are preliminary and are not evidence of household performance or guaranteed savings.
- **Operational readiness:** PostgreSQL/Redis deployment, backup/restore execution, and production security validation remain open.
- **Final demonstration:** browser interactions and screenshots are available; the uninterrupted timed walkthrough and recording are outstanding.

For evidence and scope boundaries, start with the [final demo acceptance report](backend/docs/demo/FINAL_DEMO_ACCEPTANCE.md) and [development status](DEVELOPMENT_STATUS.md).

## Tech Stack

**Backend**
- FastAPI (Python 3.11)
- SQLAlchemy + PostgreSQL
- JWT Authentication

**Mobile**
- React Native + Expo
- Expo Router
- Zustand
- Victory Native Charts

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see LICENSE file for details.
