use super::Operator;
use crate::schema::{aggregate_schema, AggregateRecord};
use arrow::array::{Float64Array, RecordBatch, StringArray};
use std::collections::HashMap;
use std::sync::Arc;

pub struct GroupAggregateOperator;

impl GroupAggregateOperator {
    pub fn new() -> Self {
        Self
    }

    fn round_2(val: f64) -> f64 {
        (val * 100.0).round() / 100.0
    }

    fn round_4(val: f64) -> f64 {
        (val * 10000.0).round() / 10000.0
    }

    pub fn aggregate(batch: &RecordBatch) -> Result<Vec<AggregateRecord>, String> {
        let num_rows = batch.num_rows();
        if num_rows == 0 {
            return Ok(Vec::new());
        }

        let member_ids = batch
            .column(batch.schema().index_of("member_id").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| "member_id column missing".to_string())?;
        let symbols = batch
            .column(batch.schema().index_of("symbol").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| "symbol column missing".to_string())?;
        let classifications = batch
            .column(batch.schema().index_of("classification").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| "classification column missing".to_string())?;
        let quantities = batch
            .column(batch.schema().index_of("quantity").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| "quantity column missing".to_string())?;
        let gross_gains = batch
            .column(batch.schema().index_of("gross_gain_inr").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| "gross_gain_inr column missing".to_string())?;
        let taxable_gains = batch
            .column(batch.schema().index_of("taxable_gain_inr").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| "taxable_gain_inr column missing".to_string())?;
        let total_taxes = batch
            .column(batch.schema().index_of("total_tax_inr").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| "total_tax_inr column missing".to_string())?;

        let mut groups: HashMap<(String, String, String), AggregateRecord> = HashMap::new();

        for i in 0..num_rows {
            let m_id = member_ids.value(i).to_string();
            let sym = symbols.value(i).to_string();
            let class = classifications.value(i).to_string();
            let qty = quantities.value(i);
            let gross = gross_gains.value(i);
            let taxable = taxable_gains.value(i);
            let tax = total_taxes.value(i);

            let key = (m_id.clone(), sym.clone(), class.clone());
            let entry = groups.entry(key).or_insert(AggregateRecord {
                member_id: m_id,
                symbol: sym,
                classification: class,
                total_quantity: 0.0,
                total_gross_gain_inr: 0.0,
                total_taxable_gain_inr: 0.0,
                total_tax_inr: 0.0,
            });

            entry.total_quantity += qty;
            entry.total_gross_gain_inr += gross;
            entry.total_taxable_gain_inr += taxable;
            entry.total_tax_inr += tax;
        }

        let mut result: Vec<AggregateRecord> = groups
            .into_values()
            .map(|mut r| {
                r.total_quantity = Self::round_4(r.total_quantity);
                r.total_gross_gain_inr = Self::round_2(r.total_gross_gain_inr);
                r.total_taxable_gain_inr = Self::round_2(r.total_taxable_gain_inr);
                r.total_tax_inr = Self::round_2(r.total_tax_inr);
                r
            })
            .collect();

        result.sort_by(|a, b| {
            a.member_id
                .cmp(&b.member_id)
                .then_with(|| a.symbol.cmp(&b.symbol))
                .then_with(|| a.classification.cmp(&b.classification))
        });

        Ok(result)
    }

    pub fn aggregates_to_batch(records: &[AggregateRecord]) -> Result<RecordBatch, String> {
        let schema = Arc::new(aggregate_schema());

        let member_ids: Vec<&str> = records.iter().map(|r| r.member_id.as_str()).collect();
        let symbols: Vec<&str> = records.iter().map(|r| r.symbol.as_str()).collect();
        let classifications: Vec<&str> = records.iter().map(|r| r.classification.as_str()).collect();
        let total_quantities: Vec<f64> = records.iter().map(|r| r.total_quantity).collect();
        let total_gross_gains: Vec<f64> = records.iter().map(|r| r.total_gross_gain_inr).collect();
        let total_taxable_gains: Vec<f64> = records.iter().map(|r| r.total_taxable_gain_inr).collect();
        let total_taxes: Vec<f64> = records.iter().map(|r| r.total_tax_inr).collect();

        RecordBatch::try_new(
            schema,
            vec![
                Arc::new(StringArray::from(member_ids)),
                Arc::new(StringArray::from(symbols)),
                Arc::new(StringArray::from(classifications)),
                Arc::new(Float64Array::from(total_quantities)),
                Arc::new(Float64Array::from(total_gross_gains)),
                Arc::new(Float64Array::from(total_taxable_gains)),
                Arc::new(Float64Array::from(total_taxes)),
            ],
        )
        .map_err(|e| e.to_string())
    }
}

impl Operator for GroupAggregateOperator {
    fn execute(&self, input: Option<RecordBatch>) -> Result<RecordBatch, String> {
        let batch = input.ok_or_else(|| "GroupAggregateOperator requires input RecordBatch".to_string())?;
        let records = Self::aggregate(&batch)?;
        Self::aggregates_to_batch(&records)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::operators::fifo_match::FIFOMatchOperator;
    use crate::schema::MatchedLotRecord;

    #[test]
    fn test_group_aggregate_basic() {
        let matched = vec![
            MatchedLotRecord {
                member_id: "father".into(),
                symbol: "RELIANCE.NS".into(),
                lot_id: "L1".into(),
                buy_date: "2023-01-15".into(),
                sell_date: "2024-03-10".into(),
                quantity: 70.0,
                buy_price: 2000.0,
                sell_price: 2500.0,
                gross_gain_inr: 35000.0,
                taxable_gain_inr: 35000.0,
                tax_rate: 0.20,
                tax_amount_inr: 7000.0,
                cess_amount_inr: 280.0,
                total_tax_inr: 7280.0,
                classification: "STCG".into(),
                holding_days: 420,
            },
        ];

        let batch = FIFOMatchOperator::matched_lots_to_batch(&matched).unwrap();
        let agg_op = GroupAggregateOperator::new();
        let agg_batch = agg_op.execute(Some(batch)).unwrap();

        assert_eq!(agg_batch.num_rows(), 1);
    }
}
