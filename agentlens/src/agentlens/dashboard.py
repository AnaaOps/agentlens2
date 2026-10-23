"""Streamlit dashboard. Launch with:  agentlens dashboard"""
import json
import os
from collections import Counter

import streamlit as st

from agentlens.storage import TraceStore

st.set_page_config(page_title="agentlens", layout="wide")
st.title("agentlens")

store = TraceStore(os.getenv("AGENTLENS_DB", "agentlens.db"))
runs = store.list_runs(limit=500)

if not runs:
    st.info("No runs recorded yet. Run an agent through agentlens first.")
    st.stop()

labels = Counter(r["failure_label"] for r in runs if r["failure_label"])
col1, col2, col3, col4 = st.columns(4)
col1.metric("Runs", len(runs))
col2.metric("Failed runs", sum(labels.values()))
col3.metric("Total tokens", sum(r["total_tokens"] for r in runs))
col4.metric("Avg latency (s)", round(sum(r["total_latency_ms"] for r in runs) / len(runs) / 1000, 2))

if labels:
    st.subheader("Failure types")
    st.bar_chart(dict(labels))

only_failed = st.checkbox("Show only failed runs")
shown = [r for r in runs if r["failure_label"]] if only_failed else runs
st.dataframe([{k: r[k] for k in ("id", "name", "status", "model", "total_tokens",
                                 "total_latency_ms", "failure_label")} for r in shown],
             )

if shown:
    chosen = st.selectbox("Inspect a run", [r["id"] for r in shown])
    spans = store.get_spans(chosen)
    depth, rows = {}, []
    for s in spans:
        depth[s["id"]] = depth.get(s["parent_id"], -1) + 1
        out = json.loads(s["output_json"]) if s["output_json"] else None
        rows.append({"step": "    " * depth[s["id"]] + f"{s['kind']}: {s['name']}",
                     "latency_ms": round(s["latency_ms"] or 0, 1),
                     "tokens_in": s["tokens_in"], "tokens_out": s["tokens_out"],
                     "error": s["error"], "output": str(out)[:200]})
    st.subheader("Timeline")
    st.dataframe(rows)
