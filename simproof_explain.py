#!/usr/bin/env python3
"""simproof explain - Regression explanation surface"""

import sys
import json
import argparse
from typing import List, Dict, Tuple
from collections import defaultdict

def kendall_tau(rank_a: List[str], rank_b: List[str]) -> float:
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

def compute_controller_variance(data: Dict[int, Dict[str, float]]) -> Dict[str, float]:
    controller_values = defaultdict(list)
    for seed, scores in data.items():
        for controller, value in scores.items():
            controller_values[controller].append(value)
    
    variances = {}
    for controller, values in controller_values.items():
        if len(values) > 1:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            cv = (variance ** 0.5) / mean if mean > 0 else 0
            variances[controller] = cv
        else:
            variances[controller] = 0.0
    return variances

def identify_primary_driver(baseline_data: Dict, current_data: Dict) -> Tuple[str, float, str]:
    baseline_var = compute_controller_variance(baseline_data)
    current_var = compute_controller_variance(current_data)
    
    variance_deltas = {}
    for controller in current_var:
        delta = current_var[controller] - baseline_var.get(controller, 0)
        variance_deltas[controller] = delta
    
    primary = max(variance_deltas, key=variance_deltas.get)
    severity = variance_deltas[primary]
    
    if severity > 0.5:
        mode = "critical_variance_increase"
    elif severity > 0.2:
        mode = "moderate_variance_increase"
    else:
        mode = "ranking_shift_without_variance_change"
    
    return primary, severity, mode

def get_evidence(baseline_data: Dict, current_data: Dict, controller: str) -> dict:
    baseline_vals = []
    current_vals = []
    
    for seed, scores in baseline_data.items():
        if controller in scores:
            baseline_vals.append(scores[controller])
    for seed, scores in current_data.items():
        if controller in scores:
            current_vals.append(scores[controller])
    
    baseline_range = [min(baseline_vals), max(baseline_vals)] if baseline_vals else [0, 0]
    current_range = [min(current_vals), max(current_vals)] if current_vals else [0, 0]
    baseline_mean = sum(baseline_vals) / len(baseline_vals) if baseline_vals else 0
    current_mean = sum(current_vals) / len(current_vals) if current_vals else 0
    range_increase = (current_range[1] - current_range[0]) / (baseline_range[1] - baseline_range[0] + 0.01) * 100
    
    return {
        "baseline_range": baseline_range,
        "current_range": current_range,
        "baseline_mean": round(baseline_mean, 2),
        "current_mean": round(current_mean, 2),
        "range_increase_percent": round(range_increase)
    }

def explain(baseline_csv: str, current_csv: str) -> dict:
    baseline_data = parse_csv(baseline_csv)
    current_data = parse_csv(current_csv)
    
    def get_ranking(data):
        seeds = list(data.keys())
        if not seeds:
            return []
        first_seed = seeds[0]
        scores = data[first_seed]
        return sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    
    baseline_ranking = get_ranking(baseline_data)
    current_ranking = get_ranking(current_data)
    
    ranking_changed = baseline_ranking != current_ranking
    flip_severity = kendall_tau(baseline_ranking, current_ranking) if ranking_changed else 0
    
    primary_driver, severity, mode = identify_primary_driver(baseline_data, current_data)
    evidence = get_evidence(baseline_data, current_data, primary_driver)
    
    baseline_var = compute_controller_variance(baseline_data)
    current_var = compute_controller_variance(current_data)
    total_current = sum(current_var.values()) or 1
    
    instability_contribution = {c: round(current_var[c] / total_current, 2) for c in current_var}
    
    if mode == "critical_variance_increase":
        recommendation = f"REJECT_MERGE: {primary_driver} shows critical variance increase (CV increased by {severity:.0%}). Investigate initialization or environment sensitivity."
    elif mode == "moderate_variance_increase":
        recommendation = f"REJECT_MERGE: {primary_driver} variance increased significantly. Run additional seeds to confirm."
    else:
        recommendation = f"REVIEW: Ranking changed but variance stable. Manual check recommended."
    
    return {
        "verdict": "REJECT_MERGE" if ranking_changed or severity > 0.2 else "ACCEPT",
        "summary": f"Ranking instability caused by {primary_driver} variance increase",
        "causal_analysis": {
            "primary_driver": primary_driver,
            "instability_contribution": instability_contribution,
            "failure_mode": mode,
            "severity": round(severity, 3)
        },
        "evidence": evidence,
        "ranking_change": {
            "baseline": baseline_ranking,
            "current": current_ranking,
            "flip_severity": round(flip_severity, 3)
        },
        "recommendation": recommendation
    }

def main():
    parser = argparse.ArgumentParser(description="Stability regression explanation")
    parser.add_argument("--baseline", required=True, help="Baseline CSV file")
    parser.add_argument("--current", required=True, help="Current CSV file")
    parser.add_argument("--output", choices=["json", "human"], default="human")
    args = parser.parse_args()
    
    with open(args.baseline) as f:
        baseline_csv = f.read()
    with open(args.current) as f:
        current_csv = f.read()
    
    result = explain(baseline_csv, current_csv)
    
    if args.output == "json":
        print(json.dumps(result, indent=2))
    else:
        print("\n" + "="*60)
        print("SIMPROOF EXPLAIN — Regression Analysis")
        print("="*60)
        print(f"Verdict: {result['verdict']}")
        print(f"Summary: {result['summary']}")
        print("\n📊 Primary Driver: " + result['causal_analysis']['primary_driver'])
        print("   Failure mode: " + result['causal_analysis']['failure_mode'])
        print("   Severity: " + str(result['causal_analysis']['severity'] * 100) + "%")
        print("\n📈 Evidence:")
        print("   Baseline range: " + str(result['evidence']['baseline_range']))
        print("   Current range:  " + str(result['evidence']['current_range']))
        print("   Range increase: " + str(result['evidence']['range_increase_percent']) + "%")
        print("\n🔄 Ranking Change:")
        print("   Baseline: " + " > ".join(result['ranking_change']['baseline']))
        print("   Current:  " + " > ".join(result['ranking_change']['current']))
        print("   Flip severity: " + str(result['ranking_change']['flip_severity']))
        print("\n💡 Recommendation:")
        print("   " + result['recommendation'])
        print("="*60 + "\n")
    
    sys.exit(1 if result["verdict"] == "REJECT_MERGE" else 0)

if __name__ == "__main__":
    main()
