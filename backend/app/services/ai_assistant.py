"""AI Assistant service for natural language energy queries."""

import os
from datetime import date, timedelta
from typing import Any

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from sqlalchemy.orm import Session

from app.services.rag_engine import get_rag_engine
from app.services.usage_analyzer import UsageAnalyzer


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
- Reference actual usage data when available
- Provide specific, actionable advice
- Mention Victorian government rebates when relevant
- Always consider the time-of-use periods: Peak (3-9pm), Shoulder (7am-3pm, 9pm-10pm), Off-Peak (10pm-7am)

When discussing costs, use these typical Victorian rates:
- Peak: ~38c/kWh
- Shoulder: ~25c/kWh
- Off-Peak: ~18c/kWh
- Daily supply: ~$1.20/day
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
            meter = self.db.query(Meter).filter(
                Meter.user_id == user_id,
                Meter.is_active == True
            ).first()
            if not meter:
                return "No meter data available for this user."
            meter_id = meter.id

        analyzer = UsageAnalyzer(self.db)
        
        # Get last 7 days of usage
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        
        try:
            daily_usage = analyzer.get_daily_usage(
                meter_id=meter_id,
                start_date=start_date,
                end_date=end_date,
                limit=7
            )
            
            if not daily_usage:
                return "No recent usage data available."

            # Build context string
            total_kwh = sum(d.total_kwh for d in daily_usage)
            total_cost = sum(d.estimated_cost for d in daily_usage)
            avg_daily = total_kwh / len(daily_usage)
            
            # Get TOU breakdown from summary
            summary = analyzer.get_usage_summary(meter_id, start_date, end_date)
            
            context = f"""User's Recent Energy Usage (last 7 days):
- Total consumption: {total_kwh:.1f} kWh
- Total estimated cost: ${total_cost:.2f}
- Average daily usage: {avg_daily:.1f} kWh/day
- Peak usage: {summary.tou_breakdown.get('peak', 0):.1f} kWh ({summary.tou_breakdown.get('peak', 0)/total_kwh*100:.0f}%)
- Shoulder usage: {summary.tou_breakdown.get('shoulder', 0):.1f} kWh
- Off-Peak usage: {summary.tou_breakdown.get('off_peak', 0):.1f} kWh

Daily breakdown:
"""
            for d in daily_usage[-5:]:  # Last 5 days
                context += f"- {d.date}: {d.total_kwh:.1f} kWh (${d.estimated_cost:.2f})\n"

            return context

        except Exception as e:
            return f"Error fetching usage data: {str(e)}"

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
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

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
            except Exception as e:
                print(f"OpenAI API error: {e}")
                # Fall through to rule-based response

        # Fallback: Rule-based response
        return self._generate_fallback_response(message, usage_context, rag_context)

    def _generate_fallback_response(
        self,
        message: str,
        usage_context: str,
        rag_context: list[str]
    ) -> str:
        """Generate a rule-based response when AI is unavailable."""
        message_lower = message.lower()

        # Bill/cost related queries
        if any(word in message_lower for word in ["bill", "cost", "expensive", "high", "save"]):
            tips = self.rag_engine.get_savings_tips("general")
            return f"""Based on Victorian energy rates, here are some ways to reduce your bill:

{chr(10).join(f'• {tip}' for tip in tips)}

{usage_context}

The biggest savings come from shifting usage to off-peak hours (10pm-7am) and reducing peak usage (3pm-9pm weekdays)."""

        # Usage/consumption queries
        if any(word in message_lower for word in ["usage", "consumption", "used", "yesterday", "today", "week"]):
            return f"""Here's a summary of your energy usage:

{usage_context}

Victorian average household usage is about 11-14 kWh per day. If you're above this, consider running appliances during off-peak hours."""

        # Solar queries
        if "solar" in message_lower:
            return """Great question about solar! Here's what you should know:

**Solar Panel Rebate (Victoria)**
• Up to $1,400 off solar panel systems
• Eligibility: Combined income under $210,000, property under $3M

**Solar Battery Rebate**
• Up to $2,950 off battery storage
• Interest-free loans available

A typical 6.6kW system can offset most daytime usage and export excess to the grid (feed-in tariff ~5-10c/kWh).

Would you like tips on maximizing solar value?"""

        # Peak/off-peak queries
        if any(word in message_lower for word in ["peak", "off-peak", "when", "best time"]):
            return """**Victorian Time-of-Use Periods:**

⚡ **Peak** (3pm-9pm weekdays): ~38c/kWh
   Avoid running heavy appliances

📊 **Shoulder** (7am-3pm, 9pm-10pm weekdays): ~25c/kWh
   OK for moderate usage

🌙 **Off-Peak** (10pm-7am + all weekends): ~18c/kWh
   Best time for dishwasher, washing machine, EV charging

**Pro tip:** Set timers on appliances to start at 10pm!"""

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
