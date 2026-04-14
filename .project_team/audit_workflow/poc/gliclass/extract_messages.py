"""Extract pre-filtered human messages to JSONL for analysis."""

import json
import re
from pathlib import Path

NOISE_PREFIXES = [
    "[Spawned by agent",
    "[Request interrupted",
    "<task-notification>",
    "You have been idle",
    "[Message from agent",
    "[Question from agent",
    "[Redirected by",
    "This session is being continued",
    "Workflow '",
    "<system-reminder>",
]

BANKS = [
    [
        (re.compile(r"\bno[,.]?\s+that'?s\b", re.I), 0.45),
        (re.compile(r"\bnot what I\b", re.I), 0.50),
        (re.compile(r"\bthat'?s not\s+(right|correct|what)\b", re.I), 0.50),
        (re.compile(r"\bthat'?s\s+wrong\b", re.I), 0.55),
        (re.compile(r"\bno[,.]?\s+(I\s+)?(said|meant|asked|wanted)\b", re.I), 0.50),
        (re.compile(r"\bwrong\b", re.I), 0.30),
        (re.compile(r"\bincorrect\b", re.I), 0.35),
        (re.compile(r"\bnot\s+correct\b", re.I), 0.40),
    ],
    [
        (re.compile(r"\bgaslighting\b", re.I), 0.70),
        (re.compile(r"\byou'?re\s+not\s+listening\b", re.I), 0.65),
        (re.compile(r"\bstop\s+(doing|it|that)\b", re.I), 0.50),
        (re.compile(r"\bI\s+already\s+(said|told|explained)\b", re.I), 0.55),
        (re.compile(r"\bhow\s+many\s+times\b", re.I), 0.55),
        (re.compile(r"\bplease\s+(just\s+)?read\b", re.I), 0.35),
        (re.compile(r"\bpay\s+attention\b", re.I), 0.55),
        (re.compile(r"\byou\s+keep\b", re.I), 0.40),
        (re.compile(r"\bfrustrat", re.I), 0.45),
    ],
    [
        (re.compile(r"\bbug\b", re.I), 0.25),
        (re.compile(r"\bbroken\b", re.I), 0.30),
        (re.compile(r"\berror\b", re.I), 0.20),
        (re.compile(r"\bcrash(es|ed|ing)?\b", re.I), 0.25),
        (re.compile(r"\bfail(s|ed|ing|ure)?\b", re.I), 0.20),
        (re.compile(r"\bdoesn'?t\s+work\b", re.I), 0.35),
        (re.compile(r"\bnot\s+working\b", re.I), 0.35),
    ],
    [
        (re.compile(r"\bI\s+said\b", re.I), 0.40),
        (re.compile(r"\bdon'?t\s+do\b", re.I), 0.40),
        (re.compile(r"\brevert\b", re.I), 0.45),
        (re.compile(r"\bundo\b", re.I), 0.35),
        (re.compile(r"\broll\s*back\b", re.I), 0.40),
        (re.compile(r"\binstead\b", re.I), 0.20),
        (re.compile(r"\bactually\b", re.I), 0.20),
        (re.compile(r"\bI\s+(meant|wanted|asked\s+for)\b", re.I), 0.40),
        (re.compile(r"\bnot\s+what\s+I\b", re.I), 0.50),
        (re.compile(r"\bshould\s+(be|have)\b", re.I), 0.20),
        (
            re.compile(r"\byou\s+(missed|forgot|skipped|ignored|overlooked)\b", re.I),
            0.50,
        ),
        (
            re.compile(
                r"\bdo(n'?t|es\s*n'?t)\s+(modify|change|touch|edit|alter)\b", re.I
            ),
            0.40,
        ),
        (re.compile(r"\bI\s+told\s+you\b", re.I), 0.50),
        (re.compile(r"\blike\s+I\s+said\b", re.I), 0.45),
    ],
]


def regex_score(text):
    scores = []
    for bank in BANKS:
        for pattern, weight in bank:
            if pattern.search(text):
                scores.append(weight)
    if not scores:
        return 0.0
    scores.sort(reverse=True)
    combined = scores[0]
    for s in scores[1:]:
        combined += s * 0.3
    return min(combined, 1.0)


def _extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )
    out = Path(__file__).parent / "messages_310.jsonl"

    msgs = []
    for f in sorted(session_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                obj.get("type") == "user"
                and obj.get("message", {}).get("role") == "user"
            ):
                content = obj["message"].get("content", "")
                text = _extract_text(content).strip()
                if not text or any(text.startswith(p) for p in NOISE_PREFIXES):
                    continue
                msgs.append(
                    {
                        "text": text,
                        "session_file": f.name,
                        "uuid": obj.get("uuid", ""),
                        "rx_score": regex_score(text),
                    }
                )

    with open(out, "w", encoding="utf-8") as fh:
        for i, m in enumerate(msgs):
            m["index"] = i
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")

    print(f"Wrote {len(msgs)} messages to {out}")
    print(f"Regex flagged (>=0.3): {sum(1 for m in msgs if m['rx_score'] >= 0.3)}")

    # Also print all messages for review
    for m in msgs:
        rx = m["rx_score"]
        flag = "*" if rx >= 0.3 else " "
        text = m["text"][:150].replace("\n", " ")
        print(f"  {m['index']:3d}{flag} rx={rx:.2f}  {text}")


if __name__ == "__main__":
    main()
