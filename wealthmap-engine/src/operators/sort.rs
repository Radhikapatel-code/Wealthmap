use super::Operator;
use arrow::array::RecordBatch;
use arrow::compute::kernels::take::take_record_batch;
use arrow::compute::{lexsort_to_indices, SortColumn, SortOptions};

pub struct SortOperator {
    sort_columns: Vec<String>,
}

impl SortOperator {
    pub fn new(sort_columns: Vec<String>) -> Self {
        Self { sort_columns }
    }

    pub fn default_fifo_sort() -> Self {
        Self {
            sort_columns: vec!["member_id".into(), "symbol".into(), "date".into()],
        }
    }
}

impl Operator for SortOperator {
    fn execute(&self, input: Option<RecordBatch>) -> Result<RecordBatch, String> {
        let batch = input.ok_or_else(|| "SortOperator requires input RecordBatch".to_string())?;

        if batch.num_rows() <= 1 {
            return Ok(batch);
        }

        let mut columns_to_sort = Vec::new();
        for col_name in &self.sort_columns {
            let col_idx = batch
                .schema()
                .index_of(col_name)
                .map_err(|e| format!("Sort column {} not found in schema: {}", col_name, e))?;

            columns_to_sort.push(SortColumn {
                values: batch.column(col_idx).clone(),
                options: Some(SortOptions {
                    descending: false,
                    nulls_first: false,
                }),
            });
        }

        let indices = lexsort_to_indices(&columns_to_sort, None).map_err(|e| e.to_string())?;
        take_record_batch(&batch, &indices).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{transactions_to_record_batch, TransactionRecord};
    use arrow::array::StringArray;

    #[test]
    fn test_sort_operator() {
        let dummy_txs = vec![
            TransactionRecord {
                transaction_id: "T2".into(),
                member_id: "father".into(),
                symbol: "RELIANCE.NS".into(),
                side: "BUY".into(),
                date: "2024-06-20".into(),
                quantity: "50".into(),
                price: "2200".into(),
                asset_class: "EQUITY".into(),
                lot_id: Some("L2".into()),
            },
            TransactionRecord {
                transaction_id: "T1".into(),
                member_id: "father".into(),
                symbol: "RELIANCE.NS".into(),
                side: "BUY".into(),
                date: "2023-01-15".into(),
                quantity: "100".into(),
                price: "2000".into(),
                asset_class: "EQUITY".into(),
                lot_id: Some("L1".into()),
            },
        ];

        let batch = transactions_to_record_batch(&dummy_txs).unwrap();
        let sort = SortOperator::default_fifo_sort();
        let sorted = sort.execute(Some(batch)).unwrap();

        let dates = sorted
            .column(sorted.schema().index_of("date").unwrap())
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();

        assert_eq!(dates.value(0), "2023-01-15");
        assert_eq!(dates.value(1), "2024-06-20");
    }
}
