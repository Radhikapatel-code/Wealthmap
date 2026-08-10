use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use std::collections::{HashMap, VecDeque};
use std::path::PathBuf;
use wealthmap_engine::concurrency::{ParallelEngine, PriceReferenceCache};
use wealthmap_engine::pipeline::EnginePipeline;
use wealthmap_engine::schema::{
    load_golden_transactions_batch, load_transactions_from_json, AggregateRecord,
    MatchedLotRecord, TransactionRecord,
};

fn get_testdata_dir() -> PathBuf {
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.push("testdata");
    p
}

// ── Naive Row-at-a-time Rust Matching Baseline ───────────────────────────
fn run_naive_row_at_a_time(
    txs: &[TransactionRecord],
) -> (Vec<MatchedLotRecord>, Vec<AggregateRecord>) {
    struct BuyLot {
        lot_id: String,
        member_id: String,
        symbol: String,
        asset_class: String,
        buy_date: String,
        remaining_qty: f64,
        buy_price: f64,
    }

    let mut queues: HashMap<(String, String), VecDeque<BuyLot>> = HashMap::new();
    let mut matched = Vec::new();

    let mut sorted_txs = txs.to_vec();
    sorted_txs.sort_by(|a, b| {
        a.member_id
            .cmp(&b.member_id)
            .then_with(|| a.symbol.cmp(&b.symbol))
            .then_with(|| a.date.cmp(&b.date))
    });

    for tx in &sorted_txs {
        let key = (tx.member_id.clone(), tx.symbol.clone());
        let qty: f64 = tx.quantity.parse().unwrap_or(0.0);
        let price: f64 = tx.price.parse().unwrap_or(0.0);

        if tx.side.eq_ignore_ascii_case("BUY") {
            queues.entry(key).or_default().push_back(BuyLot {
                lot_id: tx.lot_id.clone().unwrap_or_default(),
                member_id: tx.member_id.clone(),
                symbol: tx.symbol.clone(),
                asset_class: tx.asset_class.clone(),
                buy_date: tx.date.clone(),
                remaining_qty: qty,
                buy_price: price,
            });
        } else if tx.side.eq_ignore_ascii_case("SELL") {
            let mut sell_rem = qty;
            let queue = queues.entry(key).or_default();
            while sell_rem > 1e-7 && !queue.is_empty() {
                let lot = queue.front_mut().unwrap();
                let m_qty = f64::min(sell_rem, lot.remaining_qty);
                sell_rem -= m_qty;
                lot.remaining_qty -= m_qty;

                let gain = (price - lot.buy_price) * m_qty;
                let is_crypto = lot.asset_class == "CRYPTO";
                let tax_class = if is_crypto { "CRYPTO" } else { "STCG" };
                let tax_rate = if is_crypto { 0.30 } else { 0.20 };
                let tax_amt = gain.max(0.0) * tax_rate;

                matched.push(MatchedLotRecord {
                    member_id: tx.member_id.clone(),
                    symbol: tx.symbol.clone(),
                    lot_id: lot.lot_id.clone(),
                    buy_date: lot.buy_date.clone(),
                    sell_date: tx.date.clone(),
                    quantity: m_qty,
                    buy_price: lot.buy_price,
                    sell_price: price,
                    gross_gain_inr: gain,
                    taxable_gain_inr: gain.max(0.0),
                    tax_rate,
                    tax_amount_inr: tax_amt,
                    cess_amount_inr: tax_amt * 0.04,
                    total_tax_inr: tax_amt * 1.04,
                    classification: tax_class.into(),
                    holding_days: 100,
                });

                if lot.remaining_qty <= 1e-7 {
                    queue.pop_front();
                }
            }
        }
    }

    let mut agg_map: HashMap<(String, String, String), AggregateRecord> = HashMap::new();
    for m in &matched {
        let key = (m.member_id.clone(), m.symbol.clone(), m.classification.clone());
        let entry = agg_map.entry(key).or_insert(AggregateRecord {
            member_id: m.member_id.clone(),
            symbol: m.symbol.clone(),
            classification: m.classification.clone(),
            total_quantity: 0.0,
            total_gross_gain_inr: 0.0,
            total_taxable_gain_inr: 0.0,
            total_tax_inr: 0.0,
        });
        entry.total_quantity += m.quantity;
        entry.total_gross_gain_inr += m.gross_gain_inr;
        entry.total_taxable_gain_inr += m.taxable_gain_inr;
        entry.total_tax_inr += m.total_tax_inr;
    }

    (matched, agg_map.into_values().collect())
}

fn benchmark_pipeline(c: &mut Criterion) {
    let testdata_dir = get_testdata_dir();
    let tx_path = testdata_dir.join("golden_transactions.json");
    let batch = load_golden_transactions_batch(&tx_path).expect("Failed to load golden batch");
    let tx_records = load_transactions_from_json(&tx_path).expect("Failed to load raw txs");

    let mut group = c.benchmark_group("engine_matching");

    // 1. Batched Arrow Pipeline
    group.bench_function("arrow_batched_pipeline", |b| {
        let pipeline = EnginePipeline::new(vec![]);
        b.iter(|| {
            pipeline.run(batch.clone()).unwrap()
        });
    });

    // 2. Naive Row-at-a-time Rust
    group.bench_function("row_at_a_time_naive", |b| {
        b.iter(|| {
            run_naive_row_at_a_time(&tx_records)
        });
    });

    group.finish();
}

fn benchmark_parallel_scaling(c: &mut Criterion) {
    let testdata_dir = get_testdata_dir();
    let tx_path = testdata_dir.join("golden_transactions.json");
    let batch = load_golden_transactions_batch(&tx_path).unwrap();

    let portfolio_workload: Vec<_> = (0..100).map(|_| batch.clone()).collect();
    let cache = PriceReferenceCache::new();
    let engine = ParallelEngine::new(cache);

    let mut group = c.benchmark_group("rayon_thread_scaling");
    for threads in [1, 2, 4, 8] {
        group.bench_with_input(
            BenchmarkId::from_parameter(format!("{}_threads", threads)),
            &threads,
            |b, &t| {
                b.iter(|| {
                    engine.process_portfolios(portfolio_workload.clone(), t).unwrap()
                });
            },
        );
    }
    group.finish();
}

criterion_group!(benches, benchmark_pipeline, benchmark_parallel_scaling);
criterion_main!(benches);
