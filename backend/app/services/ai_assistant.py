"""AI Assistant service for natural language energy queries."""

import logging
import os
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

        # Get user's meter if not specified
        if meter_id is None:
            meter = (
                self.db.query(Meter)
                .filter(Meter.user_id == user_id, Meter.is_active == True)
                .first()
            )
            if not meter:
                return "No meter data available for this user."
            meter_id = meter.id

        analyzer = UsageAnalyzer(self.db)

        # Get last 7 days of usage
        end_date = date.today()
        start_date = end_date - timedelta(days=7)

        try:
            daily_usage = analyzer.get_daily_usage(
                meter_id=meter_id, start_date=start_date, end_date=end_date, limit=7
            )

            if not daily_usage:
                return "No recent usage data available."

            # Build context string
            total_kwh = sum(d.total_kwh for d in daily_usage)
            avg_daily = total_kwh / len(daily_usage)

            # Get TOU breakdown from summary
            summary = analyzer.get_usage_summary(meter_id, start_date, end_date)

            context = f"""User's Recent Energy Usage (last 7 days):
- Total consumption: {total_kwh:.1f} kWh
- Average daily usage: {avg_daily:.1f} kWh/day
- Peak usage: {summary.tou_breakdown.get("peak", 0):.1f} kWh
  ({summary.tou_breakdown.get("peak", 0) / total_kwh * 100:.0f}%)
- Shoulder usage: {summary.tou_breakdown.get("shoulder", 0):.1f} kWh
- Off-Peak usage: {summary.tou_breakdown.get("off_peak", 0):.1f} kWh

Daily breakdown:
"""
            for d in daily_usage[-5:]:  # Last 5 days
                context += f"- {d.date}: {d.total_kwh:.1f} kWh\n"

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
                return response.choices[0].message.content
            except Exception as exc:
                logger.warning(
                    "OpenAI request failed; using local assistant fallback",
                    extra={"error_type": type(exc).__name__},
                )
                # Fall through to rule-based response

        # Fallback: Rule-based response
        return self._generate_fallback_response(message, usage_context, rag_context)

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
