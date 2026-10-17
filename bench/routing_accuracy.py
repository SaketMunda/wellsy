"""Tier-2 vs tier-3 routing accuracy: does the model call `use_tools` exactly
when the request needs the user's data or an action? (step 9)

No classifier (that is step 8) — this measures the model's own tool-calling,
with the production system prompt (+ pipecat's async-tool instructions, which
the live service appends), the production routing tool, and a realistic
history: two chat turns and one completed agentic turn (calendar read), so
follow-up questions about that turn are in scope.

    .venv/bin/python bench/routing_accuracy.py --trials 3
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

TOOL = [
    ("What's on my calendar tomorrow?", True), ("Remind me to call mom tomorrow at 6 pm.", True),
    ("Book a dentist appointment on Monday at 3 pm.", True), ("Do I have any new email?", True),
    ("Draft a reply to Dana saying Thursday works, and send it.", True),
    ("Move my design review to Thursday at 2.", True), ("Add buying milk to my reminders.", True),
    ("What's Priya's email address?", True), ("Make a note that the wifi password changed.", True),
    ("Delete plan.txt from my scratch folder.", True), ("Am I free on Friday afternoon?", True),
    ("Mark the groceries reminder as done.", True), ("Read me my latest email from Dana.", True),
    ("Schedule lunch with Sam tomorrow at noon.", True), ("What notes do I have?", True),
]
NO_TOOL = [
    ("How are you today?", False), ("Tell me a fun fact.", False), ("What's the capital of Japan?", False),
    ("Tell me a short joke.", False), ("Thanks, that's helpful.", False), ("What's two plus seven?", False),
    ("Order me a pizza.", False), ("What's the weather like?", False),
    ("What did I just ask you about?", False), ("When was that design review again?", False),
    ("Can you explain what a reminder is?", False), ("Who are you?", False),
    ("Say that again, please.", False), ("Give me a word that rhymes with blue.", False),
    ("Did you just check my calendar?", False),
]


def history():
    return [
        {"role": "user", "content": "Hi Wellsy."},
        {"role": "assistant", "content": "Hi! What can I do for you?"},
        {"role": "user", "content": "What's on my calendar tomorrow?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c0", "type": "function", "function": {
            "name": "use_tools", "arguments": json.dumps({"request": "calendar tomorrow"})}}]},
        {"role": "tool", "tool_call_id": "c0", "content": json.dumps({"status": "ok", "steps": [
            {"tool": "pim.calendar_list_events", "status": "ok", "verified": True,
             "result": [{"title": "Design review", "start": "2026-10-18T15:00:00"}]}]})},
        {"role": "assistant", "content": "Tomorrow you have a design review at 3 PM."},
    ]


def call(model, sys_prompt, tools, messages, temperature, top_p):
    body = {"model": model, "messages": [{"role": "system", "content": sys_prompt}] + messages,
            "tools": tools, "reasoning_effort": "none", "max_tokens": 300, "keep_alive": -1,
            "temperature": temperature, "top_p": top_p}
    req = urllib.request.Request("http://localhost:11434/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    m = json.loads(urllib.request.urlopen(req, timeout=120).read())["choices"][0]["message"]
    return bool(m.get("tool_calls")), (m.get("content") or "")[:120]


def main() -> int:
    from pipecat.processors.aggregators.async_tool_messages import ASYNC_TOOL_INSTRUCTIONS

    from engine.agent.models import DEFAULT_MODEL
    from engine.voice.agent_bridge import TOOL_DESCRIPTION, TOOL_NAME, tools_schema
    from engine.voice.pipeline import SYSTEM_PROMPT

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--sampling", nargs="+", default=["1.0/0.95", "0.7/0.8"])
    a = ap.parse_args()
    REQ_DESC = tools_schema().standard_tools[0].properties["request"]["description"]
    tools = [{"type": "function", "function": {"name": TOOL_NAME, "description": TOOL_DESCRIPTION,
              "parameters": {"type": "object", "properties": {"request": {"type": "string", "description": REQ_DESC}},
                             "required": ["request"]}}}]
    sys_prompt = SYSTEM_PROMPT + "\n\n" + ASYNC_TOOL_INSTRUCTIONS
    out = REPO / "spec" / "results" / f"routing-accuracy-{dt.datetime.now():%Y-%m-%d-%H%M}.jsonl"
    summary = {}
    with open(out, "w") as f:
        for samp in a.sampling:
            temp, top_p = (float(x) for x in samp.split("/"))
            fn, fp, n = [], [], 0
            for say, want in TOOL + NO_TOOL:
                for t in range(a.trials):
                    got, text = call(a.model, sys_prompt, tools, history() + [{"role": "user", "content": say}],
                                     temp, top_p)
                    n += 1
                    if got != want:
                        (fn if want else fp).append(say)
                    f.write(json.dumps({"sampling": samp, "say": say, "wantTool": want, "gotTool": got,
                                        "text": text}) + "\n")
            summary[samp] = {"correct": f"{n - len(fn) - len(fp)}/{n}",
                             "missedTool (said instead of doing)": sorted(set(fn)), "missedToolCount": len(fn),
                             "spuriousTool (acted on a question)": sorted(set(fp)), "spuriousToolCount": len(fp)}
            print(samp, json.dumps(summary[samp], indent=1), flush=True)
        f.write(json.dumps({"summary": summary, "model": a.model, "trials": a.trials,
                            "method": "production system prompt + ASYNC_TOOL_INSTRUCTIONS + use_tools, "
                                      "6-message history incl. one agentic turn, /v1 reasoning_effort none"}) + "\n")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
