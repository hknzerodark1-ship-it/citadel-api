use clap::{Parser, Subcommand};
use serde::Serialize;
use std::path::PathBuf;
use anyhow::Result;

mod stability;
mod criterion_parser;

use stability::compute_stability;
use criterion_parser::load_criterion_benchmarks;

#[derive(Parser)]
#[command(name = "criterion-stability")]
#[command(about = "Benchmark ranking stability analysis")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Analyze {
        #[arg(short, long)]
        input: PathBuf,
        #[arg(short, long, default_value = "human")]
        format: String,
        #[arg(long, default_value = "1000")]
        bootstrap: usize,
        #[arg(long, default_value = "0.7")]
        threshold: f64,
    },
    Criterion {
        #[arg(short, long, default_value = "target/criterion")]
        target: PathBuf,
        #[arg(short, long, default_value = "human")]
        format: String,
        #[arg(long, default_value = "1000")]
        bootstrap: usize,
        #[arg(long, default_value = "0.7")]
        threshold: f64,
    },
    Init,
}

#[derive(Serialize)]
struct StabilityOutput {
    verdict: String,
    avg_confidence: f64,
    benchmarks: Vec<BenchmarkStability>,
    recommendation: String,
}

#[derive(Serialize)]
struct BenchmarkStability {
    name: String,
    stability: f64,
    stable: bool,
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Analyze { input, format, bootstrap, threshold } => {
            analyze_csv(&input, &format, bootstrap, threshold)
        }
        Commands::Criterion { target, format, bootstrap, threshold } => {
            analyze_criterion(&target, &format, bootstrap, threshold)
        }
        Commands::Init => {
            generate_github_action()
        }
    }
}

fn analyze_criterion(target: &PathBuf, format: &str, bootstrap: usize, threshold: f64) -> Result<()> {
    eprintln!("Loading Criterion benchmarks from: {}", target.display());
    let benchmarks = load_criterion_benchmarks(target);
    if benchmarks.is_empty() {
        eprintln!("Error: No benchmark data found in {}", target.display());
        eprintln!("Make sure you have run `cargo bench` first.");
        std::process::exit(1);
    }
    eprintln!("Found {} benchmarks", benchmarks.len());
    let sample_data: Vec<Vec<f64>> = benchmarks.iter().map(|b| b.samples.clone()).collect();
    let benchmark_names: Vec<String> = benchmarks.iter().map(|b| b.name.clone()).collect();
    let stability_scores = compute_stability(&sample_data, bootstrap);
    let avg_confidence = if stability_scores.is_empty() {
        0.0
    } else {
        stability_scores.iter().sum::<f64>() / stability_scores.len() as f64
    };
    let verdict = if avg_confidence >= threshold { "STABLE" } else { "UNSTABLE" };
    let benchmark_stability: Vec<BenchmarkStability> = benchmark_names
        .iter()
        .zip(stability_scores.iter())
        .map(|(name, score)| BenchmarkStability {
            name: name.clone(),
            stability: *score,
            stable: *score >= threshold,
        })
        .collect();
    let output = StabilityOutput {
        verdict: verdict.to_string(),
        avg_confidence,
        benchmarks: benchmark_stability,
        recommendation: if avg_confidence >= threshold {
            "Ranking is stable. Safe to use for decisions.".to_string()
        } else {
            "Ranking is unstable. Review uncertain comparisons.".to_string()
        },
    };
    if format == "json" {
        println!("{}", serde_json::to_string_pretty(&output)?);
    } else {
        print_human(&output);
    }
    if avg_confidence < threshold {
        std::process::exit(1);
    }
    Ok(())
}

fn analyze_csv(path: &PathBuf, format: &str, bootstrap: usize, threshold: f64) -> Result<()> {
    let mut reader = csv::Reader::from_path(path)?;
    let mut benchmark_data: Vec<Vec<f64>> = Vec::new();
    let mut benchmark_names: Vec<String> = Vec::new();
    let mut current_benchmark = String::new();
    let mut current_values: Vec<f64> = Vec::new();
    for result in reader.records() {
        let record = result?;
        let name = record.get(0).unwrap_or("");
        let value: f64 = record.get(2).unwrap_or("0").parse()?;
        if name != current_benchmark {
            if !current_values.is_empty() {
                benchmark_data.push(current_values.clone());
                benchmark_names.push(current_benchmark.clone());
                current_values.clear();
            }
            current_benchmark = name.to_string();
        }
        current_values.push(value);
    }
    if !current_values.is_empty() {
        benchmark_data.push(current_values);
        benchmark_names.push(current_benchmark);
    }
    if benchmark_data.is_empty() {
        eprintln!("Error: No valid data found in CSV");
        std::process::exit(1);
    }
    let stability_scores = compute_stability(&benchmark_data, bootstrap);
    let avg_confidence = stability_scores.iter().sum::<f64>() / stability_scores.len() as f64;
    let verdict = if avg_confidence >= threshold { "STABLE" } else { "UNSTABLE" };
    let benchmark_stability: Vec<BenchmarkStability> = benchmark_names
        .iter()
        .zip(stability_scores.iter())
        .map(|(name, score)| BenchmarkStability {
            name: name.clone(),
            stability: *score,
            stable: *score >= threshold,
        })
        .collect();
    let output = StabilityOutput {
        verdict: verdict.to_string(),
        avg_confidence,
        benchmarks: benchmark_stability,
        recommendation: if avg_confidence >= threshold {
            "Ranking is stable. Safe to use for decisions.".to_string()
        } else {
            "Ranking is unstable. Review uncertain comparisons.".to_string()
        },
    };
    if format == "json" {
        println!("{}", serde_json::to_string_pretty(&output)?);
    } else {
        print_human(&output);
    }
    if avg_confidence < threshold {
        std::process::exit(1);
    }
    Ok(())
}

fn generate_github_action() -> Result<()> {
    println!("name: Benchmark Stability Gate");
    println!("on: [pull_request]");
    println!("jobs:");
    println!("  stability-check:");
    println!("    runs-on: ubuntu-latest");
    println!("    steps:");
    println!("      - uses: actions/checkout@v4");
    println!("      - name: Install criterion-stability");
    println!("        run: cargo install criterion-stability-cli");
    println!("      - name: Run benchmarks");
    println!("        run: cargo bench");
    println!("      - name: Check stability");
    println!("        run: criterion-stability criterion --format json");
    Ok(())
}

fn print_human(output: &StabilityOutput) {
    println!("\n============================================================");
    println!("BENCHMARK RANK STABILITY ANALYSIS");
    println!("============================================================");
    println!("Verdict: {}", output.verdict);
    println!("Avg Confidence: {:.1}%", output.avg_confidence * 100.0);
    println!("\nBenchmarks:");
    for b in &output.benchmarks {
        let status = if b.stable { "✓" } else { "⚠️" };
        println!("  {} {}: {:.1}% stable", status, b.name, b.stability * 100.0);
    }
    println!("\nRecommendation: {}", output.recommendation);
    println!("============================================================\n");
}
