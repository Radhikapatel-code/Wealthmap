use crate::operators::aggregate::GroupAggregateOperator;
use crate::operators::fifo_match::FIFOMatchOperator;
use crate::operators::filter::{FilterOperator, Predicate};
use crate::operators::scan::ScanOperator;
use crate::operators::sort::SortOperator;
use crate::operators::Operator;
use crate::schema::{
    load_golden_transactions_batch, AggregateRecord, MatchedLotRecord,
};
use arrow::array::RecordBatch;

pub struct EnginePipeline {
    predicates: Vec<Predicate>,
}

impl EnginePipeline {
    pub fn new(predicates: Vec<Predicate>) -> Self {
        Self { predicates }
    }

    pub fn run(&self, input_batch: RecordBatch) -> Result<(Vec<MatchedLotRecord>, Vec<AggregateRecord>), String> {
        let scan = ScanOperator::new(input_batch);
        let scan_out = scan.execute(None)?;

        let filter = FilterOperator::new(self.predicates.clone());
        let filter_out = filter.execute(Some(scan_out))?;

        let sort = SortOperator::default_fifo_sort();
        let sort_out = sort.execute(Some(filter_out))?;

        let matched_lots = FIFOMatchOperator::match_transactions(&sort_out)?;
        let matched_batch = FIFOMatchOperator::matched_lots_to_batch(&matched_lots)?;

        let aggregates = GroupAggregateOperator::aggregate(&matched_batch)?;

        Ok((matched_lots, aggregates))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn get_testdata_dir() -> PathBuf {
        let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        p.push("testdata");
        p
    }

    #[test]
    fn test_full_pipeline_golden_correctness() {
        let testdata_dir = get_testdata_dir();
        let tx_path = testdata_dir.join("golden_transactions.json");
        let matched_path = testdata_dir.join("golden_matched_lots.json");
        let agg_path = testdata_dir.join("golden_aggregates.json");

        assert!(tx_path.exists(), "Golden transactions file missing at {:?}", tx_path);
        assert!(matched_path.exists(), "Golden matched lots file missing at {:?}", matched_path);
        assert!(agg_path.exists(), "Golden aggregates file missing at {:?}", agg_path);

        let input_batch = load_golden_transactions_batch(&tx_path).expect("Failed to load golden transactions");

        let expected_matched: Vec<MatchedLotRecord> = serde_json::from_str(
            &fs::read_to_string(&matched_path).expect("Failed to read expected matched lots")
        ).expect("Failed to deserialize expected matched lots");

        let expected_agg: Vec<AggregateRecord> = serde_json::from_str(
            &fs::read_to_string(&agg_path).expect("Failed to read expected aggregates")
        ).expect("Failed to deserialize expected aggregates");

        let pipeline = EnginePipeline::new(vec![]);
        let (mut actual_matched, mut actual_agg) = pipeline.run(input_batch).expect("Pipeline execution failed");

        let mut sorted_exp_matched = expected_matched.clone();
        sorted_exp_matched.sort_by(|a, b| {
            a.member_id.cmp(&b.member_id)
                .then_with(|| a.symbol.cmp(&b.symbol))
                .then_with(|| a.buy_date.cmp(&b.buy_date))
                .then_with(|| a.sell_date.cmp(&b.sell_date))
                .then_with(|| a.lot_id.cmp(&b.lot_id))
        });

        actual_matched.sort_by(|a, b| {
            a.member_id.cmp(&b.member_id)
                .then_with(|| a.symbol.cmp(&b.symbol))
                .then_with(|| a.buy_date.cmp(&b.buy_date))
                .then_with(|| a.sell_date.cmp(&b.sell_date))
                .then_with(|| a.lot_id.cmp(&b.lot_id))
        });

        assert_eq!(
            actual_matched.len(),
            sorted_exp_matched.len(),
            "Matched lot count mismatch! Actual: {}, Expected: {}",
            actual_matched.len(),
            sorted_exp_matched.len()
        );

        for (i, (act, exp)) in actual_matched.iter().zip(sorted_exp_matched.iter()).enumerate() {
            assert_eq!(act.member_id, exp.member_id, "Mismatch at row {} member_id", i);
            assert_eq!(act.symbol, exp.symbol, "Mismatch at row {} symbol", i);
            assert_eq!(act.lot_id, exp.lot_id, "Mismatch at row {} lot_id", i);
            assert_eq!(act.buy_date, exp.buy_date, "Mismatch at row {} buy_date", i);
            assert_eq!(act.sell_date, exp.sell_date, "Mismatch at row {} sell_date", i);
            assert!((act.quantity - exp.quantity).abs() < 1e-4, "Mismatch at row {} quantity", i);
            assert!((act.buy_price - exp.buy_price).abs() < 1e-2, "Mismatch at row {} buy_price", i);
            assert!((act.sell_price - exp.sell_price).abs() < 1e-2, "Mismatch at row {} sell_price", i);
            assert!((act.gross_gain_inr - exp.gross_gain_inr).abs() < 1e-2, "Mismatch at row {} gross_gain_inr", i);
            assert!((act.taxable_gain_inr - exp.taxable_gain_inr).abs() < 1e-2, "Mismatch at row {} taxable_gain_inr", i);
            assert!((act.tax_amount_inr - exp.tax_amount_inr).abs() < 1e-2, "Mismatch at row {} tax_amount_inr", i);
            assert!((act.total_tax_inr - exp.total_tax_inr).abs() < 1e-2, "Mismatch at row {} total_tax_inr", i);
            assert_eq!(act.classification, exp.classification, "Mismatch at row {} classification", i);
        }

        let mut sorted_exp_agg = expected_agg.clone();
        sorted_exp_agg.sort_by(|a, b| {
            a.member_id.cmp(&b.member_id)
                .then_with(|| a.symbol.cmp(&b.symbol))
                .then_with(|| a.classification.cmp(&b.classification))
        });

        actual_agg.sort_by(|a, b| {
            a.member_id.cmp(&b.member_id)
                .then_with(|| a.symbol.cmp(&b.symbol))
                .then_with(|| a.classification.cmp(&b.classification))
        });

        assert_eq!(actual_agg.len(), sorted_exp_agg.len(), "Aggregate record count mismatch");
        for (i, (act, exp)) in actual_agg.iter().zip(sorted_exp_agg.iter()).enumerate() {
            assert_eq!(act.member_id, exp.member_id);
            assert_eq!(act.symbol, exp.symbol);
            assert_eq!(act.classification, exp.classification);
            assert!((act.total_quantity - exp.total_quantity).abs() < 1e-4);
            assert!((act.total_gross_gain_inr - exp.total_gross_gain_inr).abs() < 1e-2);
            assert!((act.total_taxable_gain_inr - exp.total_taxable_gain_inr).abs() < 1e-2);
            assert!((act.total_tax_inr - exp.total_tax_inr).abs() < 1e-2);
        }
    }
}
