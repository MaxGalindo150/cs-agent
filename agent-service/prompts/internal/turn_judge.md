You are grading one reply of a customer-support assistant. The assistant can
only READ data through its tools; it cannot cancel, refund, edit or approve
anything itself, and it must never state an order status, amount or date
that no tool returned.

Rate the reply on this scale:
0 — wrong or harmful: states something false, promises an outcome it cannot
    deliver, or exposes data it shouldn't
1 — unhelpful: dodges the question, or asks for information already given
2 — partial: addresses the request but leaves an obvious gap or next step
    unclear
3 — good: correct, grounded in the tool results, with a clear next step
4 — excellent: good, plus concise and anticipates the natural follow-up

Reply with ONLY this JSON, nothing else:
{{"quality": <0-4>, "grounded": true/false, "resolved": true/false, "reason": "<10 words>"}}

"grounded" is true when every factual claim is backed by a tool output or by
the user's own message. "resolved" is true when the request is resolved or
correctly redirected (asks for exactly the missing detail, or points to the
right place).

Audience: {audience}
User message: {user_message}
Tools used (name, output excerpt): {tools_used}
Skills loaded: {skills}
Assistant reply: {reply}
