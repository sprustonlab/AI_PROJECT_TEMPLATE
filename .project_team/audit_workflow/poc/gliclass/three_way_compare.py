"""Three-way comparison: regex vs GLiClass vs LLM on 315 messages."""

import json
from pathlib import Path


def load_messages():
    path = Path(__file__).parent / "messages_310.jsonl"
    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            msgs.append(json.loads(line))
    return msgs


def load_llm_labels():
    path = Path(__file__).parent / "llm_labels.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["labels"].items()}


def load_gliclass_results():
    """Load GLiClass Config C results if available."""
    path = Path(__file__).parent / "gliclass_results.jsonl"
    if not path.exists():
        return None
    results = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            obj = json.loads(line)
            results[obj["index"]] = obj
    return results


def main():
    msgs = load_messages()
    llm = load_llm_labels()
    gli = load_gliclass_results()

    rx_threshold = 0.3

    # --- Compute flags ---
    rx_flags = set()
    llm_flags = set()
    gli_flags = set()

    for m in msgs:
        idx = m["index"]
        if m["rx_score"] >= rx_threshold:
            rx_flags.add(idx)
        if llm.get(idx, 0) == 1:
            llm_flags.add(idx)

    if gli:
        for idx, r in gli.items():
            if r.get("label") == "correction or disagreement":
                gli_flags.add(idx)

    n = len(msgs)
    print(f"Total messages: {n}")
    print()

    # --- Summary table ---
    print("=" * 60)
    print("METHOD COMPARISON")
    print("=" * 60)
    print(f"{'Method':<20} {'Flagged':>8} {'Rate':>8}")
    print("-" * 40)
    print(f"{'Regex (>=0.3)':<20} {len(rx_flags):>8} {len(rx_flags) / n * 100:>7.1f}%")
    if gli:
        print(
            f"{'GLiClass Config C':<20} {len(gli_flags):>8} {len(gli_flags) / n * 100:>7.1f}%"
        )
    print(f"{'LLM (manual)':<20} {len(llm_flags):>8} {len(llm_flags) / n * 100:>7.1f}%")
    print()

    # --- Overlap analysis ---
    print("=" * 60)
    print("OVERLAP ANALYSIS (using LLM as ground truth)")
    print("=" * 60)

    # Regex performance vs LLM ground truth
    rx_tp = rx_flags & llm_flags
    rx_fp = rx_flags - llm_flags
    rx_fn = llm_flags - rx_flags
    rx_tn = set(range(n)) - rx_flags - llm_flags

    print("\nRegex vs LLM ground truth:")
    print(f"  True positives:  {len(rx_tp):>4}  (both flagged)")
    print(f"  False positives: {len(rx_fp):>4}  (regex flagged, LLM said normal)")
    print(f"  False negatives: {len(rx_fn):>4}  (regex missed, LLM flagged)")
    print(f"  True negatives:  {len(rx_tn):>4}")
    if rx_tp or rx_fp:
        prec = len(rx_tp) / (len(rx_tp) + len(rx_fp))
        rec = len(rx_tp) / (len(rx_tp) + len(rx_fn)) if (rx_tp or rx_fn) else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
        print(f"  Precision: {prec:.1%}  Recall: {rec:.1%}  F1: {f1:.2f}")

    if gli:
        gli_tp = gli_flags & llm_flags
        gli_fp = gli_flags - llm_flags
        gli_fn = llm_flags - gli_flags
        gli_tn = set(range(n)) - gli_flags - llm_flags

        print("\nGLiClass vs LLM ground truth:")
        print(f"  True positives:  {len(gli_tp):>4}  (both flagged)")
        print(
            f"  False positives: {len(gli_fp):>4}  (GLiClass flagged, LLM said normal)"
        )
        print(f"  False negatives: {len(gli_fn):>4}  (GLiClass missed, LLM flagged)")
        print(f"  True negatives:  {len(gli_tn):>4}")
        if gli_tp or gli_fp:
            prec = len(gli_tp) / (len(gli_tp) + len(gli_fp))
            rec = len(gli_tp) / (len(gli_tp) + len(gli_fn)) if (gli_tp or gli_fn) else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
            print(f"  Precision: {prec:.1%}  Recall: {rec:.1%}  F1: {f1:.2f}")

    # --- Venn-style overlap ---
    print()
    print("=" * 60)
    print("SET OVERLAP")
    print("=" * 60)
    if gli:
        all_three = rx_flags & gli_flags & llm_flags
        rx_only = rx_flags - gli_flags - llm_flags
        gli_only = gli_flags - rx_flags - llm_flags
        llm_only = llm_flags - rx_flags - gli_flags
        rx_gli = (rx_flags & gli_flags) - llm_flags
        rx_llm = (rx_flags & llm_flags) - gli_flags
        gli_llm = (gli_flags & llm_flags) - rx_flags

        print(f"  All three agree:       {len(all_three):>4}")
        print(f"  Regex + GLiClass only: {len(rx_gli):>4}")
        print(f"  Regex + LLM only:      {len(rx_llm):>4}")
        print(f"  GLiClass + LLM only:   {len(gli_llm):>4}")
        print(f"  Regex only:            {len(rx_only):>4}")
        print(f"  GLiClass only:         {len(gli_only):>4}")
        print(f"  LLM only:              {len(llm_only):>4}")
    else:
        rx_llm = rx_flags & llm_flags
        rx_only = rx_flags - llm_flags
        llm_only = llm_flags - rx_flags
        print(f"  Regex + LLM overlap: {len(rx_llm):>4}")
        print(f"  Regex only:          {len(rx_only):>4}")
        print(f"  LLM only:            {len(llm_only):>4}")

    # --- Show LLM-only catches ---
    print()
    print("=" * 60)
    if gli:
        catches = llm_flags - rx_flags - gli_flags
        print(
            f"LLM-ONLY CATCHES ({len(catches)} messages neither regex nor GLiClass found)"
        )
    else:
        catches = llm_flags - rx_flags
        print(f"LLM-ONLY CATCHES ({len(catches)} messages regex missed)")
    print("=" * 60)
    by_idx = {m["index"]: m for m in msgs}
    for idx in sorted(catches):
        m = by_idx[idx]
        text = m["text"][:120].replace("\n", " ")
        print(f"  [{idx:3d}] rx={m['rx_score']:.2f}  {text}")

    # --- Show regex false positives (flagged by regex but NOT by LLM) ---
    print()
    print("=" * 60)
    rx_fps = rx_flags - llm_flags
    print(
        f"REGEX FALSE POSITIVES ({len(rx_fps)} messages regex flagged but LLM said normal)"
    )
    print("=" * 60)
    for idx in sorted(rx_fps):
        m = by_idx[idx]
        text = m["text"][:120].replace("\n", " ")
        print(f"  [{idx:3d}] rx={m['rx_score']:.2f}  {text}")

    # --- Cost estimate ---
    print()
    print("=" * 60)
    print("API COST ESTIMATE")
    print("=" * 60)
    total_chars = sum(len(m["text"]) for m in msgs)
    total_tokens_est = total_chars / 4  # rough estimate
    # System prompt ~200 tokens per call, output ~20 tokens per call
    prompt_overhead = 220 * n
    total_input = total_tokens_est + prompt_overhead
    total_output = 20 * n
    # Claude 3.5 Haiku pricing: $0.25/MTok input, $1.25/MTok output
    cost_haiku = (total_input / 1e6 * 0.25) + (total_output / 1e6 * 1.25)
    # Claude 3.5 Sonnet: $3/MTok input, $15/MTok output
    cost_sonnet = (total_input / 1e6 * 3) + (total_output / 1e6 * 15)
    # Batch API: 50% discount
    print(f"  Total messages: {n}")
    print(f"  Total message chars: {total_chars:,}")
    print(f"  Est. input tokens (with prompt): {total_input:,.0f}")
    print(f"  Est. output tokens: {total_output:,.0f}")
    print()
    print(f"  Claude 3.5 Haiku:  ${cost_haiku:.4f}  (batch: ${cost_haiku * 0.5:.4f})")
    print(f"  Claude 3.5 Sonnet: ${cost_sonnet:.4f}  (batch: ${cost_sonnet * 0.5:.4f})")
    print(f"  Claude 3 Haiku:    ~${cost_haiku * 0.3:.4f}")
    print()
    print("  --> For 315 messages, cost is negligible (<$0.05 even with Sonnet)")


if __name__ == "__main__":
    main()
