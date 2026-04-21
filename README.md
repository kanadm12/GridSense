# GridSense

**Grid-Aware Energy Copilot for Victorian Households**

GridSense helps Australian households optimize their electricity usage by analyzing smart meter data, providing real-time recommendations, and predicting the best times to use energy.

## Features

- **NEM12 Data Import** - Upload your smart meter data from energy retailers
- **Usage Analytics** - Visualize consumption by day, hour, and time-of-use periods
- **Smart Recommendations** - Get personalized tips to reduce costs
- **Cost Estimation** - See estimated costs based on Victorian tariffs

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

## Development Roadmap

- [x] Phase 1: MVP (NEM12 parser, visualization, basic recommendations)
- [ ] Phase 2: Intelligence Layer (weather integration, demand forecasting)
- [ ] Phase 3: Decision Engine (optimization algorithms, scheduling)
- [ ] Phase 4: Real-Time (live meter integration, notifications)
- [ ] Phase 5: Automation (IoT integration, smart device control)

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
