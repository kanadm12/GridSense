"""AI Assistant service for natural language energy queries."""

import logging
import os
import re
from datetime import date, timedelta

try:
    from openai import OpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from sqlalchemy.orm import Session

from app.services.rag_engine import get_rag_engine
from app.services.usage_analyzer import UsageAnalyzer

logger = logging.getLogger(__name__)

UNSUPPORTED_FINANCIAL_CLAIM = re.compile(
    r"(?:"
    r"[$]\s*\d|"
    r"\bAUD\s*\$?\s*\d|"
    r"\b(?:save|saves|saving|savings|reduce|reduction|lower|cut|decrease)\b"
    r".{0,45}\b\d+(?:\.\d+)?\s*(?:%|percent|kwh|dollars?|aud)|"
    r"\b(?:bill|cost|charge|usage|consumption)\b.{0,35}"
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|kwh)"
    r")",
    re.IGNORECASE,
)


SYSTEM_PROMPT = """You are GridSense, an AI energy assistant for Victorian households in Australia.
You help users understand their electricity usage, save money, and make smart energy decisions.

Your expertise includes:
- Victorian Time-of-Use (TOU) electricity tariffs
- Energy efficiency tips for Australian homes
- Solar panel and battery information
- Interpreting smart meter data
- Seasonal energy advice for Melbourne's climate

Guidelines:
- Be concise but helpful (2-3 paragraphs max unless asked for detail)
- Use Australian English spelling
- Describe interval readings as observed imports, not as appliance-level facts
- Reference actual usage data when available and distinguish it from inferences
- Provide specific, actionable advice
- Mention Victorian government rebates when relevant
- Shared GridSense time windows are examples, not proof of a user's retailer tariff.
- Do not invent rates, bills, or dollar savings.
- This chat request contains no calculation-evidence object. Do not state quantified
  customer savings, bill reductions, or tariff impacts.
- Discuss money only when a verified configured tariff is explicitly in context.
- Chat is explanatory guidance, not an authoritative bill.
- Direct users to tariff and bill comparison screens for estimates, not retailer-issued bills.
"""


class AIAssistant:
    """AI-powered energy assistant using OpenAI."""

    def __init__(self, db: Session):
        """Initialize the AI assistant.

        Args:
            db: Database session for fetching user data
        """
        self.db = db
        self.rag_engine = get_rag_engine()
        self._client = None

    def _get_client(self):
        """Get or create OpenAI client."""
        if self._client is None and HAS_OPENAI:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self._client = OpenAI(api_key=api_key)
        return self._client

    def _get_usage_context(self, user_id: int, meter_id: int | None = None) -> str:
        """Get user's recent usage data for context."""
        from app.models.meter import Meter

        meter_query = self.db.query(Meter).filter(
            Meter.user_id == user_id,
            Meter.is_active.is_(True),
        )
        if meter_id is not None:
            meter_query = meter_query.filter(Meter.id == meter_id)
        meter = meter_query.first()
        if meter is None:
            return "No meter data available for this user."
        meter_id = meter.id

        analyzer = UsageAnalyzer(self.db)

        # Use only the seven fully completed dates immediately before today.
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=6)

        try:
            daily_usage = analyzer.get_daily_usage(
                meter_id=meter_id, start_date=start_date, end_date=end_date, limit=7
            )

            expected_dates = {
                start_date + timedelta(days=offset) for offset in range(7)
            }
            if (
                len(daily_usage) != 7
                or {day.date for day in daily_usage} != expected_dates
                or any(
                    day.coverage_status != "complete"
                    or day.provenance_status != "measured"
                    or day.unresolved_direction_count
                    or day.legacy_direction_unverified_count
                    for day in daily_usage
                )
            ):
                return (
                    "Recent usage context is unavailable because seven complete, "
                    "measured, direction-confirmed local days are not available."
                )

            total_kwh = sum(day.observed_eligible_kwh for day in daily_usage)
            avg_daily = total_kwh / 7
            peak_kwh = sum(day.peak_kwh for day in daily_usage)
            shoulder_kwh = sum(day.shoulder_kwh for day in daily_usage)
            off_peak_kwh = sum(day.off_peak_kwh for day in daily_usage)

            context = f"""User's Recent Energy Usage (last 7 days):
- Eligible measured imports: {total_kwh:.1f} kWh
- Average daily usage: {avg_daily:.1f} kWh/day
- Shared GridSense peak-window imports: {peak_kwh:.1f} kWh
- Shared GridSense shoulder-window imports: {shoulder_kwh:.1f} kWh
- Shared GridSense off-peak-window imports: {off_peak_kwh:.1f} kWh
These shared time windows are not proof of the user's retailer tariff.

Daily breakdown:
"""
            for d in daily_usage[-5:]:  # Last 5 days
                context += f"- {d.date}: {d.observed_eligible_kwh:.1f} kWh eligible imports\n"

            return context

        except Exception as exc:
            logger.warning(
                "Unable to build assistant usage context",
                extra={"meter_id": meter_id, "error_type": type(exc).__name__},
            )
            return "Usage context is temporarily unavailable."

    async def chat(
        self,
        user_id: int,
        message: str,
        conversation_history: list[dict] | None = None,
        meter_id: int | None = None,
    ) -> str:
        """Process a chat message and return AI response.

        Args:
            user_id: The user's ID for fetching their data
            message: The user's message
            conversation_history: Previous messages for context
            meter_id: Specific meter to analyze (optional)

        Returns:
            AI-generated response
        """
        # Get relevant knowledge from RAG
        rag_context = self.rag_engine.search(message, k=3)
        rag_text = "\n\n".join(rag_context) if rag_context else ""

        # Get user's usage data
        usage_context = self._get_usage_context(user_id, meter_id)

        # Build the full context
        full_context = f"""RELEVANT KNOWLEDGE:
{rag_text}

USER'S DATA:
{usage_context}
"""

        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Context:\n{full_context}"},
        ]

        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-6:]:  # Last 6 messages for context
                messages.append(
                    {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                )

        # Add current message
        messages.append({"role": "user", "content": message})

        # Try OpenAI API
        client = self._get_client()
        if client:
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  # Cost-effective model
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7,
                )
                content = response.choices[0].message.content or ""
                return self._guard_generated_response(content, usage_context)
            except Exception as exc:
                logger.warning(
                    "OpenAI request failed; using local assistant fallback",
                    extra={"error_type": type(exc).__name__},
                )
                # Fall through to rule-based response

        # Fallback: Rule-based response
        return self._generate_fallback_response(message, usage_context, rag_context)

    @staticmethod
    def _guard_generated_response(
        response: str, usage_context: str = ""
    ) -> str:
        """Replace unsupported customer financial claims with a safe limitation."""
        context_kwh = {
            float(value)
            for value in re.findall(
                r"\b(\d+(?:\.\d+)?)\s*kwh\b",
                usage_context,
                re.IGNORECASE,
            )
        }
        response_kwh = [
            float(value)
            for value in re.findall(
                r"\b(\d+(?:\.\d+)?)\s*kwh\b",
                response,
                re.IGNORECASE,
            )
        ]
        if UNSUPPORTED_FINANCIAL_CLAIM.search(response) or any(
            value not in context_kwh for value in response_kwh
        ):
            return (
                "I can't quantify a customer-specific bill or savings impact from "
                "this chat because no deterministic calculation evidence was supplied. "
                "Please use the tariff and bill-comparison views for supported estimates."
            )
        return response

    def _generate_fallback_response(
        self, message: str, usage_context: str, rag_context: list[str]
    ) -> str:
        """Generate a rule-based response when AI is unavailable."""
        message_lower = message.lower()

        # Bill/cost related queries
        if any(word in message_lower for word in ["bill", "cost", "expensive", "high", "save"]):
            tips = self.rag_engine.get_savings_tips("general")
            return f"""Here are general energy-use ideas to consider.
They are not a bill calculation or prediction of your savings:

{chr(10).join(f"• {tip}" for tip in tips)}

{usage_context}

I can't quantify a cost change without your current tariff and a specific flexible load.
Use your tariff settings and bill comparison for an estimate; it is not a retailer-issued bill."""

        # Usage/consumption queries
        if any(
            word in message_lower
            for word in ["usage", "consumption", "used", "yesterday", "today", "week"]
        ):
            return f"""Here's a summary of your observed energy use:

{usage_context}

Interval totals do not identify individual appliances.
Compare changes with your own history; a general usage figure is not a diagnosis
of inefficiency."""

        # Solar queries
        if "solar" in message_lower:
            return """Great question about solar! Here's what you should know:

**Solar Panel Rebate (Victoria)**
• Up to $1,400 off solar panel systems
• Eligibility: Combined income under $210,000, property under $3M

**Solar Battery Rebate**
• Up to $2,950 off battery storage
• Interest-free loans available

Solar generation, self-consumption, and export value depend on the installed
system and the user's actual tariff. Interval imports alone cannot establish those values.

Would you like tips on maximizing solar value?"""

        # Peak/off-peak queries
        if any(word in message_lower for word in ["peak", "off-peak", "when", "best time"]):
            return """**Example GridSense time windows** (local times; check your retailer plan):

Peak is often represented as 3pm-9pm on weekdays, shoulder as 7am-3pm and 9pm-10pm,
and off-peak as 10pm-7am and weekends. Actual retailer windows and rates can differ.

These intervals alone do not establish that an appliance can be shifted or that doing
so would save money. Check your configured tariff and the appliance's requirements."""

        # Default response with context
        context_snippet = rag_context[0] if rag_context else ""
        return f"""I can help you with energy-related questions about:
• Understanding your usage patterns
• Reducing your electricity bill
• Victorian TOU tariffs
• Solar panels and rebates
• Smart home automation

{context_snippet}

What would you like to know more about?"""


def get_ai_assistant(db: Session) -> AIAssistant:
    """Factory function to create an AI assistant instance."""
    return AIAssistant(db)
