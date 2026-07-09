import time
import json
from datetime import date
import httpx
from typing import List, Dict, Any
from opentelemetry import trace
from opentelemetry.metrics import Counter, Histogram
from app.config import settings
from app.core.telemetry import get_tracer, get_meter
import structlog

logger = structlog.get_logger(__name__)

_tracer = get_tracer()
_meter = get_meter()
recommendations_counter: Counter = _meter.create_counter(
    "recommendations_generated_total",
    description="Total number of cost optimization recommendations generated",
)
analysis_duration: Histogram = _meter.create_histogram(
    "analysis_duration_seconds",
    description="Duration of AI analysis calls",
    unit="s",
)

ZEN_API_URL = "https://opencode.ai/zen/v1/chat/completions"

SYSTEM_PROMPT = """You are an AWS Cloud Cost Optimization Expert with 15 years of experience.

Your job is to analyze AWS resources and identify:
1. **Over-provisioned resources** — instances larger than needed for their workload
2. **Unused resources** — orphaned EBS volumes, unattached EIPs, idle load balancers
3. **Misconfigurations** — missing auto-shutdown tags, non-GP3 volumes, no backup plans
4. **Reserved Instance opportunities** — resources running for >30 days
5. **Right-sizing recommendations** — specific instance type changes with cost impact

For each issue, provide:
- The resource identifier
- The issue type
- A clear explanation
- Estimated monthly savings in USD
- A specific fix command (AWS CLI)

Output as a JSON array. Each recommendation must have:
- resource_id: string
- resource_type: string
- issue: string
- severity: "critical" | "high" | "medium" | "low"
- explanation: string
- estimated_monthly_savings: number
- fix_command: string
"""


class AiAnalyzer:
    def __init__(self):
        self.api_key = settings.zen_api_key
        self.model = settings.zen_model or "zen-1"
        self.client = httpx.AsyncClient(timeout=120.0)

    async def analyze(self, resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError(
                "ZEN_API_KEY is not configured — set APP_ZEN_API_KEY environment variable"
            )

        start = time.monotonic()
        with _tracer.start_as_current_span("ai_analyze") as span:
            span.set_attribute("resource_count", len(resources))

            today = date.today()
            resource_text = (
                f"Today's date: {today.isoformat()}\n"
                f"IMPORTANT: Use current AWS pricing and instance types available as of {today.isoformat()}.\n"
                f"Do NOT use outdated pricing — if a price looks wrong, use today's AWS public pricing.\n\n"
                f"AWS Resources to analyze:\n{json.dumps(resources, indent=2)}"
            )
            span.set_attribute("prompt_length", len(resource_text))

            try:
                response = await self.client.post(
                    ZEN_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": resource_text},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 32768,
                    },
                )
                response.raise_for_status()
                raw_body = response.text
                logger.info(
                    "zen_api_response",
                    status_code=response.status_code,
                    body_length=len(raw_body),
                )
                if not raw_body.strip():
                    raise RuntimeError("ZEN API returned empty response body")
                data = response.json()
                message = data["choices"][0]["message"]
                content = message.get("content") or message.get("reasoning_content", "")

                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                recommendations = json.loads(content)
                span.set_attribute("recommendation_count", len(recommendations))
                recommendations_counter.add(len(recommendations))
                analysis_duration.record(time.monotonic() - start)
                return recommendations
            except httpx.HTTPStatusError as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise RuntimeError(
                    f"ZEN API returned {e.response.status_code}: {e.response.text[:500]}"
                )
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise RuntimeError(
                    f"ZEN API returned an unexpected response format: {e}"
                )
