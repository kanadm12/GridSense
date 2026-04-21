"""RAG (Retrieval Augmented Generation) engine for energy knowledge base."""

import os
from pathlib import Path
from typing import Any

try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import Chroma
    from langchain_openai import OpenAIEmbeddings
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

from app.config import get_settings

settings = get_settings()

# Victorian energy knowledge base - embedded directly for simplicity
ENERGY_KNOWLEDGE_BASE = """
# Victorian Energy Tariffs and Time-of-Use Information

## Time-of-Use (TOU) Periods
Victorian electricity retailers typically use these TOU periods:
- **Peak**: 3pm - 9pm weekdays (highest rates, ~35-45c/kWh)
- **Shoulder**: 7am - 3pm and 9pm - 10pm weekdays (medium rates, ~20-28c/kWh)
- **Off-Peak**: 10pm - 7am all days, all day weekends (lowest rates, ~15-20c/kWh)

## Major Victorian Retailers
1. **AGL**: Peak ~38c/kWh, Shoulder ~25c/kWh, Off-Peak ~18c/kWh
2. **Origin Energy**: Peak ~40c/kWh, Shoulder ~26c/kWh, Off-Peak ~17c/kWh
3. **EnergyAustralia**: Peak ~42c/kWh, Shoulder ~24c/kWh, Off-Peak ~16c/kWh
4. **Red Energy**: Peak ~36c/kWh, Shoulder ~23c/kWh, Off-Peak ~19c/kWh
5. **Simply Energy**: Peak ~35c/kWh, Shoulder ~22c/kWh, Off-Peak ~18c/kWh

## Supply Charges
Daily supply charges typically range from $1.00 to $1.50 per day.

# Energy Saving Tips for Victorian Households

## Heating and Cooling (40% of energy use)
- Set heating to 18-20°C and cooling to 24-26°C
- Use ceiling fans before air conditioning
- Close curtains/blinds during hot afternoons
- Seal gaps around doors and windows
- Service your AC annually for efficiency

## Hot Water (25% of energy use)
- Set temperature to 60°C (not higher)
- Take shorter showers (4 minutes saves ~$100/year)
- Fix dripping taps promptly
- Consider a heat pump hot water system

## Appliances (15% of energy use)
- Run dishwasher and washing machine during off-peak hours
- Use cold water for laundry when possible
- Only run full loads
- Choose appliances with high energy star ratings

## Standby Power (10% of energy use)
- Turn off devices at the wall when not in use
- Use power boards with switches
- Standby can cost $100+ per year

# Solar Victoria Programs

## Solar Panel Rebate
- Up to $1,400 rebate on solar panel systems
- Eligibility: Combined household income under $210,000
- Property value under $3 million
- Must use an approved retailer

## Solar Battery Rebate  
- Up to $2,950 rebate on battery storage
- Must have solar panels installed
- Interest-free loans available

## Solar Hot Water Rebate
- Up to $1,000 for solar/heat pump hot water
- Replace existing electric or gas systems

# Grid Demand Response

## What is Demand Response?
When grid demand is high (usually hot summer afternoons), reducing usage helps:
- Prevent blackouts
- Lower wholesale electricity prices
- Reduce need for expensive gas peaker plants

## How to Participate
- Sign up with your retailer's demand response program
- Receive alerts to reduce usage during critical periods
- Earn bill credits for participation

# Appliance Energy Usage Guide

## High Energy Appliances
- Air conditioner: 2-5 kWh per hour
- Electric heater: 1-2.4 kWh per hour
- Pool pump: 1-2 kWh per hour
- Clothes dryer: 2-5 kWh per load
- Electric oven: 2-2.5 kWh per hour

## Medium Energy Appliances
- Dishwasher: 1-2 kWh per cycle
- Washing machine: 0.5-2.5 kWh per load
- Refrigerator: 1-2 kWh per day
- TV (large): 0.1-0.4 kWh per hour

## Low Energy Appliances
- LED lights: 0.01 kWh per hour
- Phone charger: 0.01 kWh per charge
- Laptop: 0.05 kWh per hour

# Understanding Your Bill

## Bill Components
1. **Usage charges**: kWh used × rate per kWh
2. **Supply charge**: Daily connection fee
3. **Concessions**: Government rebates if eligible
4. **GST**: 10% on total

## Victorian Energy Compare
Use the government's Victorian Energy Compare website to find the best deal.
Average Victorian household uses 4,000-5,000 kWh per year.

# Seasonal Considerations

## Summer
- Peak demand days often on days above 35°C
- Pre-cool your home before 3pm (off-peak rates)
- Consider demand response programs
- Solar produces most energy in summer

## Winter
- Heating is biggest energy cost
- Use sun for passive heating during day
- Layer up before turning on heater
- Gas heating may be cheaper than electric
"""


class RAGEngine:
    """Retrieval Augmented Generation engine using ChromaDB."""

    def __init__(self):
        """Initialize the RAG engine with embedded knowledge base."""
        self._vectorstore = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazily initialize the vector store."""
        if self._initialized:
            return True
            
        if not HAS_LANGCHAIN:
            return False
            
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return False

        try:
            # Split knowledge base into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
                separators=["\n\n", "\n", ". ", " ", ""]
            )
            chunks = text_splitter.split_text(ENERGY_KNOWLEDGE_BASE)

            # Create embeddings and vector store
            embeddings = OpenAIEmbeddings(openai_api_key=api_key)
            self._vectorstore = Chroma.from_texts(
                texts=chunks,
                embedding=embeddings,
                collection_name="gridsense_knowledge"
            )
            self._initialized = True
            return True
        except Exception as e:
            print(f"Failed to initialize RAG engine: {e}")
            return False

    def search(self, query: str, k: int = 3) -> list[str]:
        """Search the knowledge base for relevant context.

        Args:
            query: The user's question
            k: Number of relevant chunks to return

        Returns:
            List of relevant text chunks
        """
        if not self._ensure_initialized():
            # Fallback: simple keyword matching
            return self._fallback_search(query, k)

        try:
            docs = self._vectorstore.similarity_search(query, k=k)
            return [doc.page_content for doc in docs]
        except Exception as e:
            print(f"RAG search failed: {e}")
            return self._fallback_search(query, k)

    def _fallback_search(self, query: str, k: int = 3) -> list[str]:
        """Simple keyword-based fallback when RAG is unavailable."""
        query_lower = query.lower()
        sections = ENERGY_KNOWLEDGE_BASE.split("\n\n")
        
        scored_sections = []
        for section in sections:
            section_lower = section.lower()
            # Count keyword matches
            keywords = query_lower.split()
            score = sum(1 for kw in keywords if kw in section_lower)
            if score > 0:
                scored_sections.append((score, section.strip()))
        
        # Sort by score and return top k
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        return [section for _, section in scored_sections[:k]]

    def get_tariff_context(self) -> str:
        """Get tariff-specific context for cost calculations."""
        return """Victorian TOU Rates (typical):
- Peak (3pm-9pm weekdays): ~38c/kWh
- Shoulder (7am-3pm, 9pm-10pm weekdays): ~25c/kWh  
- Off-Peak (10pm-7am all days, weekends): ~18c/kWh
- Daily supply charge: ~$1.20/day"""

    def get_savings_tips(self, category: str = "general") -> list[str]:
        """Get energy saving tips for a category."""
        tips_map = {
            "heating": [
                "Set heating to 18-20°C - each degree higher adds 10% to heating costs",
                "Seal gaps around doors and windows to prevent heat loss",
                "Use curtains to insulate windows at night",
            ],
            "cooling": [
                "Set cooling to 24-26°C - each degree lower adds 10% to cooling costs",
                "Pre-cool your home before 3pm when rates are lower",
                "Use ceiling fans first - they use 1/50th the energy of AC",
            ],
            "appliances": [
                "Run dishwasher and washing machine after 10pm (off-peak)",
                "Turn off standby power - it can cost $100+ per year",
                "Only run full loads in dishwasher and washing machine",
            ],
            "general": [
                "Shift heavy usage to off-peak hours (10pm-7am)",
                "Compare energy plans at Victorian Energy Compare",
                "Consider solar panels - up to $1,400 rebate available",
            ],
        }
        return tips_map.get(category, tips_map["general"])


# Singleton instance
_rag_engine: RAGEngine | None = None


def get_rag_engine() -> RAGEngine:
    """Get or create the RAG engine singleton."""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine
