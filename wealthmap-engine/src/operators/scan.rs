use super::Operator;
use arrow::array::RecordBatch;

pub struct ScanOperator {
    batch: RecordBatch,
}

impl ScanOperator {
    pub fn new(batch: RecordBatch) -> Self {
        Self { batch }
    }
}

impl Operator for ScanOperator {
    fn execute(&self, _input: Option<RecordBatch>) -> Result<RecordBatch, String> {
        Ok(self.batch.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{transactions_to_record_batch, TransactionRecord};

    #[test]
    fn test_scan_operator() {
        let dummy_txs = vec![TransactionRecord {
            transaction_id: "T1".into(),
            member_id: "M1".into(),
            symbol: "RELIANCE.NS".into(),
            side: "BUY".into(),
            date: "2024-01-01".into(),
            quantity: "10".into(),
            price: "2000".into(),
            asset_class: "EQUITY".into(),
            lot_id: Some("L1".into()),
        }];
        let batch = transactions_to_record_batch(&dummy_txs).unwrap();
        let scan = ScanOperator::new(batch.clone());
        let output = scan.execute(None).unwrap();
        assert_eq!(output.num_rows(), 1);
        assert_eq!(output.schema(), batch.schema());
    }
}
