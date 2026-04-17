use rand::Rng;
use rand::seq::SliceRandom;
use rand::thread_rng;

/// Compute ranking stability from raw sample data
/// Returns a vector of stability scores (0.0 to 1.0) for each benchmark
/// Higher score = more stable ranking
pub fn compute_stability(samples: &[Vec<f64>], bootstrap_samples: usize) -> Vec<f64> {
    if samples.is_empty() || samples.len() < 2 {
        return vec![1.0; samples.len()];
    }

    let n_benchmarks = samples.len();
    let mut rng = thread_rng();
    
    // Track how many times each benchmark appears in each rank position
    let mut rank_counts = vec![vec![0; n_benchmarks]; n_benchmarks];
    
    for _ in 0..bootstrap_samples {
        // Resample with replacement for each benchmark
        let resampled_means: Vec<f64> = samples
            .iter()
            .map(|bench_samples| {
                if bench_samples.is_empty() {
                    0.0
                } else {
                    // Resample with replacement
                    let n = bench_samples.len();
                    let mut resampled = Vec::with_capacity(n);
                    for _ in 0..n {
                        let idx = rng.gen::<usize>() % n;
                        resampled.push(bench_samples[idx]);
                    }
                    resampled.iter().sum::<f64>() / resampled.len() as f64
                }
            })
            .collect();
        
        // Get ranking order (higher mean = better rank)
        let mut indices: Vec<usize> = (0..n_benchmarks).collect();
        indices.sort_by(|&a, &b| resampled_means[b].partial_cmp(&resampled_means[a]).unwrap());
        
        // Record rank positions
        for (rank, &idx) in indices.iter().enumerate() {
            rank_counts[idx][rank] += 1;
        }
    }
    
    // Calculate stability: probability that each benchmark appears in its most common rank
    let mut stability = vec![0.0; n_benchmarks];
    for i in 0..n_benchmarks {
        let max_count = *rank_counts[i].iter().max().unwrap_or(&0);
        stability[i] = max_count as f64 / bootstrap_samples as f64;
    }
    
    stability
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_perfect_stability() {
        // Three benchmarks with non-overlapping distributions
        let samples = vec![
            vec![100.0, 101.0, 99.0],   // Benchmark A - highest
            vec![50.0, 51.0, 49.0],     // Benchmark B - middle
            vec![10.0, 11.0, 9.0],      // Benchmark C - lowest
        ];
        let stability = compute_stability(&samples, 500);
        // All should be stable (always in same rank)
        assert!(stability[0] > 0.95);
        assert!(stability[1] > 0.95);
        assert!(stability[2] > 0.95);
    }

    #[test]
    fn test_unstable_ranking() {
        // Two benchmarks with overlapping distributions
        let samples = vec![
            vec![50.0, 51.0, 49.0, 52.0],
            vec![50.0, 49.0, 51.0, 48.0],
        ];
        let stability = compute_stability(&samples, 500);
        // Stability should be around 0.5 (random)
        assert!(stability[0] < 0.7);
        assert!(stability[1] < 0.7);
    }
}
