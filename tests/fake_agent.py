"""Agente de mentira para las pruebas: apunta lo que recibe y contesta como la CLI de verdad."""
import json
import os
import sys
import time

kind, log = sys.argv[1], sys.argv[2]
args = sys.argv[3:]
sys.stdin.reconfigure(encoding="utf-8")
stdin = sys.stdin.read() if kind == "claude" else ""
with open(log, "w", encoding="utf-8") as f:
    json.dump({"args": args, "stdin": stdin, "agent": os.environ.get("UNI_AGENT")}, f)


def say(d):
    print(json.dumps(d), flush=True)


def delta(text, **extra):
    say({"type": "stream_event", "event": {"type": "content_block_delta",
                                           "delta": {"type": "text_delta", "text": text}}, **extra})


text = stdin if kind == "claude" else args[-1]
if "duerme" in text:
    delta("Empiezo")
    time.sleep(30)
elif "rompe" in text:
    print("no es json: algo va mal", flush=True)
    sys.exit(3)
elif kind == "claude":
    say({"type": "stream_event", "event": {"type": "message_start"}})
    delta("Hola ")
    delta("AYUDANTE", parent_tool_use_id="x")
    say({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls", "description": "Lista"}}]}})
    say({"type": "stream_event", "event": {"type": "message_start"}})
    delta("mundo")
    say({"type": "result", "subtype": "success", "result": "Hola mundo"})
else:
    say({"event": "init", "conversation_id": "11111111-2222-3333-4444-555555555555"})
    say({"event": "step_update", "step_update": {"step_type": "run_command", "step_index": 1, "command": "dir"}})
    say({"event": "step_update", "step_update": {"step_type": "run_command", "step_index": 1, "command": "dir"}})
    say({"event": "step_update", "step_update": {"step_type": "agent_response", "text_delta": "Listo"}})
    say({"event": "result", "result": {"status": "SUCCESS", "response": "Listo"}})
