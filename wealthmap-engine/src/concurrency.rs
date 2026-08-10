use crate::pipeline::EnginePipeline;
use crate::schema::{AggregateRecord, MatchedLotRecord};
use arrow::array::RecordBatch;
use rayon::ThreadPoolBuilder;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

#[derive(Clone, Default)]
pub struct PriceReferenceCache {
    prices: Arc<RwLock<HashMap<String, f64>>>,
}

impl PriceReferenceCache {
    pub fn new() -> Self {
        Self {
            prices: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn set_price(&self, symbol: impl Into<String>, price: f64) {
        if let Ok(mut lock) = self.prices.write() {
            lock.insert(symbol.into(), price);
        }
    }

    pub fn get_price(&self, symbol: &str) -> Option<f64> {
        self.prices.read().ok()?.get(symbol).copied()
    }
}

pub struct ParallelEngine {
    #[allow(dead_code)]
    cache: PriceReferenceCache,
}

impl ParallelEngine {
    pub fn new(cache: PriceReferenceCache) -> Self {
        Self { cache }
    }

    pub fn process_portfolios(
        &self,
        portfolio_batches: Vec<RecordBatch>,
        num_threads: usize,
    ) -> Result<Vec<(Vec<MatchedLotRecord>, Vec<AggregateRecord>)>, String> {
        let pool = ThreadPoolBuilder::new()
            .num_threads(num_threads)
            .build()
            .map_err(|e| format!("Failed to build Rayon threadpool: {}", e))?;

        pool.install(|| {
            use rayon::prelude::*;
            portfolio_batches
                .into_par_iter()
                .map(|batch| {
                    let pipeline = EnginePipeline::new(vec![]);
                    pipeline.run(batch)
                })
                .collect()
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::load_golden_transactions_batch;
    use std::path::PathBuf;

    fn get_testdata_dir() -> PathBuf {
        let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        p.push("testdata");
        p
    }

    #[test]
    fn test_concurrent_execution_correctness() {
        let testdata_dir = get_testdata_dir();
        let tx_path = testdata_dir.join("golden_transactions.json");
        let batch = load_golden_transactions_batch(&tx_path).unwrap();

        // Create 20 synthetic portfolio workload batches
        let portfolio_batches: Vec<_> = (0..20).map(|_| batch.clone()).collect();

        let cache = PriceReferenceCache::new();
        cache.set_price("RELIANCE.NS", 2800.0);
        cache.set_price("INFY.NS", 1750.0);

        let engine = ParallelEngine::new(cache);
        let results = engine.process_portfolios(portfolio_batches, 4).unwrap();

        assert_eq!(results.len(), 20);
        for (matched, agg) in &results {
            assert_eq!(matched.len(), 7);
            assert_eq!(agg.len(), 5);
        }
    }
}
