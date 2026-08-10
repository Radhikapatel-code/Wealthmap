use super::Operator;
use crate::schema::{matched_lot_schema, MatchedLotRecord};
use arrow::array::{Array, Float64Array, Int32Array, RecordBatch, StringArray};
use chrono::NaiveDate;
use std::collections::{HashMap, VecDeque};
use std::sync::Arc;

#[allow(dead_code)]
#[derive(Debug, Clone)]
struct OpenBuyLot {
    lot_id: String,
    member_id: String,
    symbol: String,
    asset_class: String,
    buy_date: String,
    remaining_quantity: f64,
    buy_price: f64,
}

pub struct FIFOMatchOperator;

impl FIFOMatchOperator {
    pub fn new() -> Self {
        Self
    }

    fn round_2(val: f64) -> f64 {
        (val * 100.0).round() / 100.0
    }

    pub fn match_transactions(batch: &RecordBatch) -> Result<Vec<MatchedLotRecord>, String> {
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
        let sides = batch
            .column(batch.schema().index_of("side").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| "side column missing".to_string())?;
        let dates = batch
            .column(batch.schema().index_of("date").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| "date column missing".to_string())?;
        let quantities = batch
            .column(batch.schema().index_of("quantity").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| "quantity column missing".to_string())?;
        let prices = batch
            .column(batch.schema().index_of("price").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| "price column missing".to_string())?;
        let asset_classes = batch
            .column(batch.schema().index_of("asset_class").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| "asset_class column missing".to_string())?;
        let lot_ids = batch
            .column(batch.schema().index_of("lot_id").map_err(|e| e.to_string())?)
            .as_any()
            .downcast_ref::<StringArray>()
            .ok_or_else(|| "lot_id column missing".to_string())?;

        let mut queues: HashMap<(String, String), VecDeque<OpenBuyLot>> = HashMap::new();
        let mut matched_lots = Vec::new();

        for i in 0..num_rows {
            let m_id = member_ids.value(i).to_string();
            let sym = symbols.value(i).to_string();
            let side = sides.value(i);
            let date_str = dates.value(i).to_string();
            let qty = quantities.value(i);
            let price = prices.value(i);
            let a_class = asset_classes.value(i).to_string();
            let l_id = if lot_ids.is_valid(i) {
                lot_ids.value(i).to_string()
            } else {
                format!("LOT-{}-{}", sym, i)
            };

            let key = (m_id.clone(), sym.clone());

            if side.eq_ignore_ascii_case("BUY") {
                queues.entry(key).or_default().push_back(OpenBuyLot {
                    lot_id: l_id,
                    member_id: m_id,
                    symbol: sym,
                    asset_class: a_class,
                    buy_date: date_str,
                    remaining_quantity: qty,
                    buy_price: price,
                });
            } else if side.eq_ignore_ascii_case("SELL") {
                let mut sell_remaining = qty;
                let sell_date = NaiveDate::parse_from_str(&date_str, "%Y-%m-%d")
                    .map_err(|e| format!("Invalid date {}: {}", date_str, e))?;

                let buy_queue = queues.get_mut(&key).ok_or_else(|| {
                    format!("Cannot sell {} units — no buy lots found for {}/{}", qty, m_id, sym)
                })?;

                while sell_remaining > 1e-7 {
                    if buy_queue.is_empty() {
                        let total_avail: f64 = buy_queue.iter().map(|l| l.remaining_quantity).sum();
                        return Err(format!(
                            "Cannot sell {} units — only {} available for {}/{}",
                            qty, total_avail, m_id, sym
                        ));
                    }

                    let front_lot = buy_queue.front_mut().unwrap();
                    let matched_qty = f64::min(sell_remaining, front_lot.remaining_quantity);
                    sell_remaining -= matched_qty;
                    front_lot.remaining_quantity -= matched_qty;

                    let buy_date = NaiveDate::parse_from_str(&front_lot.buy_date, "%Y-%m-%d")
                        .map_err(|e| format!("Invalid buy date {}: {}", front_lot.buy_date, e))?;
                    let holding_days = (sell_date - buy_date).num_days() as i32;

                    let gross_gain = Self::round_2((price - front_lot.buy_price) * matched_qty);

                    let (tax_class, tax_rate) = if front_lot.asset_class == "CRYPTO" {
                        ("CRYPTO".to_string(), 0.30)
                    } else if holding_days >= 365 {
                        ("LTCG".to_string(), 0.125)
                    } else {
                        ("STCG".to_string(), 0.20)
                    };

                    let taxable_gain = f64::max(gross_gain, 0.0);
                    let tax_amount = Self::round_2(taxable_gain * tax_rate);
                    let cess_amount = Self::round_2(tax_amount * 0.04);
                    let total_tax = tax_amount + cess_amount;

                    matched_lots.push(MatchedLotRecord {
                        member_id: m_id.clone(),
                        symbol: sym.clone(),
                        lot_id: front_lot.lot_id.clone(),
                        buy_date: front_lot.buy_date.clone(),
                        sell_date: date_str.clone(),
                        quantity: Self::round_2(matched_qty),
                        buy_price: front_lot.buy_price,
                        sell_price: price,
                        gross_gain_inr: gross_gain,
                        taxable_gain_inr: taxable_gain,
                        tax_rate,
                        tax_amount_inr: tax_amount,
                        cess_amount_inr: cess_amount,
                        total_tax_inr: total_tax,
                        classification: tax_class,
                        holding_days,
                    });

                    if front_lot.remaining_quantity <= 1e-7 {
                        buy_queue.pop_front();
                    } else {
                        front_lot.lot_id = format!("{}_R", front_lot.lot_id);
                    }
                }
            }
        }

        Ok(matched_lots)
    }

    pub fn matched_lots_to_batch(matched_lots: &[MatchedLotRecord]) -> Result<RecordBatch, String> {
        let schema = Arc::new(matched_lot_schema());

        let member_ids: Vec<&str> = matched_lots.iter().map(|l| l.member_id.as_str()).collect();
        let symbols: Vec<&str> = matched_lots.iter().map(|l| l.symbol.as_str()).collect();
        let lot_ids: Vec<&str> = matched_lots.iter().map(|l| l.lot_id.as_str()).collect();
        let buy_dates: Vec<&str> = matched_lots.iter().map(|l| l.buy_date.as_str()).collect();
        let sell_dates: Vec<&str> = matched_lots.iter().map(|l| l.sell_date.as_str()).collect();
        let quantities: Vec<f64> = matched_lots.iter().map(|l| l.quantity).collect();
        let buy_prices: Vec<f64> = matched_lots.iter().map(|l| l.buy_price).collect();
        let sell_prices: Vec<f64> = matched_lots.iter().map(|l| l.sell_price).collect();
        let gross_gains: Vec<f64> = matched_lots.iter().map(|l| l.gross_gain_inr).collect();
        let taxable_gains: Vec<f64> = matched_lots.iter().map(|l| l.taxable_gain_inr).collect();
        let tax_rates: Vec<f64> = matched_lots.iter().map(|l| l.tax_rate).collect();
        let tax_amounts: Vec<f64> = matched_lots.iter().map(|l| l.tax_amount_inr).collect();
        let cess_amounts: Vec<f64> = matched_lots.iter().map(|l| l.cess_amount_inr).collect();
        let total_taxes: Vec<f64> = matched_lots.iter().map(|l| l.total_tax_inr).collect();
        let classifications: Vec<&str> = matched_lots.iter().map(|l| l.classification.as_str()).collect();
        let holding_days: Vec<i32> = matched_lots.iter().map(|l| l.holding_days).collect();

        RecordBatch::try_new(
            schema,
            vec![
                Arc::new(StringArray::from(member_ids)),
                Arc::new(StringArray::from(symbols)),
                Arc::new(StringArray::from(lot_ids)),
                Arc::new(StringArray::from(buy_dates)),
                Arc::new(StringArray::from(sell_dates)),
                Arc::new(Float64Array::from(quantities)),
                Arc::new(Float64Array::from(buy_prices)),
                Arc::new(Float64Array::from(sell_prices)),
                Arc::new(Float64Array::from(gross_gains)),
                Arc::new(Float64Array::from(taxable_gains)),
                Arc::new(Float64Array::from(tax_rates)),
                Arc::new(Float64Array::from(tax_amounts)),
                Arc::new(Float64Array::from(cess_amounts)),
                Arc::new(Float64Array::from(total_taxes)),
                Arc::new(StringArray::from(classifications)),
                Arc::new(Int32Array::from(holding_days)),
            ],
        )
        .map_err(|e| e.to_string())
    }
}

impl Operator for FIFOMatchOperator {
    fn execute(&self, input: Option<RecordBatch>) -> Result<RecordBatch, String> {
        let batch = input.ok_or_else(|| "FIFOMatchOperator requires input RecordBatch".to_string())?;
        let matched = Self::match_transactions(&batch)?;
        Self::matched_lots_to_batch(&matched)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{transactions_to_record_batch, TransactionRecord};

    #[test]
    fn test_fifo_matching_basic() {
        let txs = vec![
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
            TransactionRecord {
                transaction_id: "T2".into(),
                member_id: "father".into(),
                symbol: "RELIANCE.NS".into(),
                side: "SELL".into(),
                date: "2024-03-10".into(),
                quantity: "70".into(),
                price: "2500".into(),
                asset_class: "EQUITY".into(),
                lot_id: None,
            },
        ];

        let batch = transactions_to_record_batch(&txs).unwrap();
        let fifo = FIFOMatchOperator::new();
        let matched_batch = fifo.execute(Some(batch)).unwrap();

        assert_eq!(matched_batch.num_rows(), 1);
        let qty_col = matched_batch
            .column(matched_batch.schema().index_of("quantity").unwrap())
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap();
        assert_eq!(qty_col.value(0), 70.0);
    }
}
