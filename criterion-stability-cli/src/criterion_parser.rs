//! Parse Criterion benchmark output files

use serde::Deserialize;
use std::path::Path;
use std::fs;
use glob::glob;

#[derive(Debug, Deserialize)]
pub struct CriterionSample {
    #[allow(dead_code)]
    pub iteration_count: Vec<f64>,
    pub times: Vec<f64>,
}

#[derive(Debug, Deserialize)]
pub struct CriterionBenchmark {
    pub data: CriterionSample,
}

pub struct CriterionData {
    pub name: String,
    pub samples: Vec<f64>,
}

pub fn load_criterion_benchmarks(target_dir: &Path) -> Vec<CriterionData> {
    let mut results = Vec::new();
    let pattern = target_dir.join("*").join("new").join("samples.json");
    let pattern_str = pattern.to_string_lossy();

    for entry in glob(&pattern_str).expect("Failed to read glob pattern") {
        match entry {
            Ok(samples_path) => {
                let benchmark_name = samples_path
                    .parent()
                    .and_then(|p| p.parent())
                    .and_then(|p| p.parent())
                    .and_then(|p| p.file_name())
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_else(|| "unknown".to_string());

                match parse_samples_file(&samples_path) {
                    Ok(samples) => {
                        if !samples.is_empty() {
                            results.push(CriterionData {
                                name: benchmark_name,
                                samples,
                            });
                        }
                    }
                    Err(e) => eprintln!("Warning: Failed to parse {}: {}", samples_path.display(), e),
                }
            }
            Err(e) => eprintln!("Glob error: {}", e),
        }
    }

    results
}

fn parse_samples_file(path: &Path) -> Result<Vec<f64>, String> {
    let content = fs::read_to_string(path).map_err(|e| format!("Failed to read {}: {}", path.display(), e))?;
    let benchmark: CriterionBenchmark = serde_json::from_str(&content).map_err(|e| format!("Failed to parse JSON: {}", e))?;
    Ok(benchmark.data.times)
}
