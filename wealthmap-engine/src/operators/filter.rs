use super::Operator;
use arrow::array::{Array, BooleanArray, RecordBatch, StringArray};
use arrow::compute::filter_record_batch;

#[derive(Debug, Clone)]
pub enum Predicate {
    Equals { column: String, value: String },
    DateRange { column: String, start: String, end: String },
}

pub struct FilterOperator {
    predicates: Vec<Predicate>,
}

impl FilterOperator {
    pub fn new(predicates: Vec<Predicate>) -> Self {
        Self { predicates }
    }
}

impl Operator for FilterOperator {
    fn execute(&self, input: Option<RecordBatch>) -> Result<RecordBatch, String> {
        let batch = input.ok_or_else(|| "FilterOperator requires input RecordBatch".to_string())?;

        if self.predicates.is_empty() || batch.num_rows() == 0 {
            return Ok(batch);
        }

        let num_rows = batch.num_rows();
        let mut mask = vec![true; num_rows];

        for pred in &self.predicates {
            match pred {
                Predicate::Equals { column, value } => {
                    let col_idx = batch
                        .schema()
                        .index_of(column)
                        .map_err(|e| format!("Column {} not found in schema: {}", column, e))?;
                    let arr = batch
                        .column(col_idx)
                        .as_any()
                        .downcast_ref::<StringArray>()
                        .ok_or_else(|| format!("Column {} is not StringArray", column))?;

                    for i in 0..num_rows {
                        if mask[i] {
                            let match_val = arr.value(i);
                            if match_val != value {
                                mask[i] = false;
                            }
                        }
                    }
                }
                Predicate::DateRange { column, start, end } => {
                    let col_idx = batch
                        .schema()
                        .index_of(column)
                        .map_err(|e| format!("Column {} not found in schema: {}", column, e))?;
                    let arr = batch
                        .column(col_idx)
                        .as_any()
                        .downcast_ref::<StringArray>()
                        .ok_or_else(|| format!("Column {} is not StringArray", column))?;

                    for i in 0..num_rows {
                        if mask[i] {
                            let date_val = arr.value(i);
                            if date_val < start.as_str() || date_val > end.as_str() {
                                mask[i] = false;
                            }
                        }
                    }
                }
            }
        }

        let bool_array = BooleanArray::from(mask);
        filter_record_batch(&batch, &bool_array).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{transactions_to_record_batch, TransactionRecord};

    #[test]
    fn test_filter_operator() {
        let dummy_txs = vec![
            TransactionRecord {
                transaction_id: "T1".into(),
                member_id: "father".into(),
                symbol: "RELIANCE.NS".into(),
                side: "BUY".into(),
                date: "2024-01-01".into(),
                quantity: "10".into(),
                price: "2000".into(),
                asset_class: "EQUITY".into(),
                lot_id: Some("L1".into()),
            },
            TransactionRecord {
                transaction_id: "T2".into(),
                member_id: "father".into(),
                symbol: "INFY.NS".into(),
                side: "BUY".into(),
                date: "2024-02-01".into(),
                quantity: "20".into(),
                price: "1500".into(),
                asset_class: "EQUITY".into(),
                lot_id: Some("L2".into()),
            },
        ];

        let batch = transactions_to_record_batch(&dummy_txs).unwrap();

        let filter = FilterOperator::new(vec![Predicate::Equals {
            column: "symbol".into(),
            value: "RELIANCE.NS".into(),
        }]);

        let filtered = filter.execute(Some(batch)).unwrap();
        assert_eq!(filtered.num_rows(), 1);

        let symbol_col = filtered
            .column(filtered.schema().index_of("symbol").unwrap())
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        assert_eq!(symbol_col.value(0), "RELIANCE.NS");
    }
}
