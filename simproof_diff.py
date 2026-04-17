#!/usr/bin/env python3
"""simproof diff - CI-native stability regression detection"""

import sys
import json
import argparse
from typing import List, Dict

def kendall_tau(rank_a: List[str], rank_b: List[str]) -> float:
    """Kendall Tau distance (0=identical, 1=reversed)"""
    if rank_a == rank_b:
        return 0.0
    
    pos_a = {c: i for i, c in enumerate(rank_a)}
    pos_b = {c: i for i, c in enumerate(rank_b)}
    
    controllers = list(pos_a.keys())
    discordant = 0
    total = 0
    
    for i in range(len(controllers)):
        for j in range(i+1, len(controllers)):
            total += 1
            if (pos_a[controllers[i]] - pos_a[controllers[j]]) * \
               (pos_b[controllers[i]] - pos_b[controllers[j]]) < 0:
                discordant += 1
    
    return discordant / total if total > 0 else 0.0

def parse_csv(csv_text: str) -> Dict[int, Dict[str, float]]:
    """Parse CSV into {seed: {controller: metric}}"""
    lines = csv_text.strip().split('\n')
    if len(lines) < 2:
        raise ValueError("Need at least 2 rows")
    
    headers = lines[0].split(',')
    try:
        ctrl_idx = headers.index('controller')
        seed_idx = headers.index('seed')
        metric_idx = headers.index('failure_time')
    except ValueError:
        raise ValueError("CSV needs: controller, seed, failure_time")
    
    data = {}
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) < 3:
            continue
        controller = parts[ctrl_idx].strip()
        seed = int(parts[seed_idx].strip())
        metric = float(parts[metric_idx].strip())
        
        if seed not in data:
            data[seed] = {}
        data[seed][controller] = metric
    
    return data

def compute_stability(csv_text: str) -> dict:
    """Compute stability metrics from CSV"""
    data = parse_csv(csv_text)
    
    rankings = {}
    for seed, scores in data.items():
        ranking = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
        rankings[seed] = ranking
    
    seeds = list(rankings.keys())
    if len(seeds) < 2:
        return {"error": "Need at least 2 seeds"}
    
    distances = []
    for i in range(len(seeds)):
        for j in range(i+1, len(seeds)):
            distances.append(kendall_tau(rankings[seeds[i]], rankings[seeds[j]]))
    
    instability_score = sum(distances) / len(distances) if distances else 0
    
    return {
        "instability_score": round(instability_score, 3),
        "reference_ranking": rankings[seeds[0]],
        "n_seeds": len(seeds)
    }

def diff(baseline_csv: str, current_csv: str) -> dict:
    """Compare stability between baseline and current"""
    baseline = compute_stability(baseline_csv)
    current = compute_stability(current_csv)
    
    if "error" in baseline or "error" in current:
        return {"error": baseline.get("error") or current.get("error")}
    
    instability_delta = current["instability_score"] - baseline["instability_score"]
    regression_detected = instability_delta > 0.1
    
    ranking_changed = baseline["reference_ranking"] != current["reference_ranking"]
    flip_severity = kendall_tau(baseline["reference_ranking"], current["reference_ranking"])
    
    recommendation = "REJECT_MERGE" if regression_detected or ranking_changed else "ACCEPT"
    
    return {
        "regression_detected": regression_detected,
        "instability_delta": round(instability_delta, 3),
        "baseline_instability": baseline["instability_score"],
        "current_instability": current["instability_score"],
        "ranking_changed": ranking_changed,
        "flip_severity": round(flip_severity, 3),
        "baseline_ranking": baseline["reference_ranking"],
        "current_ranking": current["reference_ranking"],
        "recommendation": recommendation
    }

def main():
    parser = argparse.ArgumentParser(description="Stability diff engine")
    parser.add_argument("--baseline", required=True, help="Baseline CSV file")
    parser.add_argument("--current", required=True, help="Current CSV file")
    parser.add_argument("--output", choices=["json", "human"], default="human")
    args = parser.parse_args()
    
    with open(args.baseline) as f:
        baseline_csv = f.read()
    with open(args.current) as f:
        current_csv = f.read()
    
    result = diff(baseline_csv, current_csv)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    
    if args.output == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*50}")
        print("STABILITY DIFF REPORT")
        print(f"{'='*50}")
        print(f"Regression detected: {result['regression_detected']}")
        print(f"Instability delta: {result['instability_delta']:+.3f}")
        print(f"Ranking changed: {result['ranking_changed']}")
        print(f"Flip severity: {result['flip_severity']}")
        print(f"Recommendation: {result['recommendation']}")
        print(f"{'='*50}\n")
    
    sys.exit(1 if result["recommendation"] == "REJECT_MERGE" else 0)

if __name__ == "__main__":
    main()
