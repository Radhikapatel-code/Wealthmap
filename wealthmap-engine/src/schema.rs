use arrow::array::{
    Float64Array, RecordBatch, StringArray,
};
use arrow::datatypes::{DataType, Field, Schema};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::sync::Arc;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransactionRecord {
    pub transaction_id: String,
    pub member_id: String,
    pub symbol: String,
    pub side: String,
    pub date: String,
    pub quantity: String,
    pub price: String,
    pub asset_class: String,
    pub lot_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MatchedLotRecord {
    pub member_id: String,
    pub symbol: String,
    pub lot_id: String,
    pub buy_date: String,
    pub sell_date: String,
    pub quantity: f64,
    pub buy_price: f64,
    pub sell_price: f64,
    pub gross_gain_inr: f64,
    pub taxable_gain_inr: f64,
    pub tax_rate: f64,
    pub tax_amount_inr: f64,
    pub cess_amount_inr: f64,
    pub total_tax_inr: f64,
    pub classification: String,
    pub holding_days: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AggregateRecord {
    pub member_id: String,
    pub symbol: String,
    pub classification: String,
    pub total_quantity: f64,
    pub total_gross_gain_inr: f64,
    pub total_taxable_gain_inr: f64,
    pub total_tax_inr: f64,
}

pub fn transaction_schema() -> Schema {
    Schema::new(vec![
        Field::new("transaction_id", DataType::Utf8, false),
        Field::new("member_id", DataType::Utf8, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("side", DataType::Utf8, false),
        Field::new("date", DataType::Utf8, false),
        Field::new("quantity", DataType::Float64, false),
        Field::new("price", DataType::Float64, false),
        Field::new("asset_class", DataType::Utf8, false),
        Field::new("lot_id", DataType::Utf8, true),
    ])
}

pub fn matched_lot_schema() -> Schema {
    Schema::new(vec![
        Field::new("member_id", DataType::Utf8, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("lot_id", DataType::Utf8, false),
        Field::new("buy_date", DataType::Utf8, false),
        Field::new("sell_date", DataType::Utf8, false),
        Field::new("quantity", DataType::Float64, false),
        Field::new("buy_price", DataType::Float64, false),
        Field::new("sell_price", DataType::Float64, false),
        Field::new("gross_gain_inr", DataType::Float64, false),
        Field::new("taxable_gain_inr", DataType::Float64, false),
        Field::new("tax_rate", DataType::Float64, false),
        Field::new("tax_amount_inr", DataType::Float64, false),
        Field::new("cess_amount_inr", DataType::Float64, false),
        Field::new("total_tax_inr", DataType::Float64, false),
        Field::new("classification", DataType::Utf8, false),
        Field::new("holding_days", DataType::Int32, false),
    ])
}

pub fn aggregate_schema() -> Schema {
    Schema::new(vec![
        Field::new("member_id", DataType::Utf8, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("classification", DataType::Utf8, false),
        Field::new("total_quantity", DataType::Float64, false),
        Field::new("total_gross_gain_inr", DataType::Float64, false),
        Field::new("total_taxable_gain_inr", DataType::Float64, false),
        Field::new("total_tax_inr", DataType::Float64, false),
    ])
}

pub fn load_transactions_from_json<P: AsRef<Path>>(path: P) -> Result<Vec<TransactionRecord>, String> {
    let content = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let records: Vec<TransactionRecord> = serde_json::from_str(&content).map_err(|e| e.to_string())?;
    Ok(records)
}

pub fn transactions_to_record_batch(txs: &[TransactionRecord]) -> Result<RecordBatch, String> {
    let schema = Arc::new(transaction_schema());

    let tx_ids: Vec<&str> = txs.iter().map(|t| t.transaction_id.as_str()).collect();
    let member_ids: Vec<&str> = txs.iter().map(|t| t.member_id.as_str()).collect();
    let symbols: Vec<&str> = txs.iter().map(|t| t.symbol.as_str()).collect();
    let sides: Vec<&str> = txs.iter().map(|t| t.side.as_str()).collect();
    let dates: Vec<&str> = txs.iter().map(|t| t.date.as_str()).collect();
    let quantities: Vec<f64> = txs
        .iter()
        .map(|t| t.quantity.parse::<f64>().unwrap_or(0.0))
        .collect();
    let prices: Vec<f64> = txs
        .iter()
        .map(|t| t.price.parse::<f64>().unwrap_or(0.0))
        .collect();
    let asset_classes: Vec<&str> = txs.iter().map(|t| t.asset_class.as_str()).collect();
    let lot_ids: Vec<Option<&str>> = txs.iter().map(|t| t.lot_id.as_deref()).collect();

    let batch = RecordBatch::try_new(
        schema,
        vec![
            Arc::new(StringArray::from(tx_ids)),
            Arc::new(StringArray::from(member_ids)),
            Arc::new(StringArray::from(symbols)),
            Arc::new(StringArray::from(sides)),
            Arc::new(StringArray::from(dates)),
            Arc::new(Float64Array::from(quantities)),
            Arc::new(Float64Array::from(prices)),
            Arc::new(StringArray::from(asset_classes)),
            Arc::new(StringArray::from(lot_ids)),
        ],
    )
    .map_err(|e| e.to_string())?;

    Ok(batch)
}

pub fn load_golden_transactions_batch<P: AsRef<Path>>(path: P) -> Result<RecordBatch, String> {
    let records = load_transactions_from_json(path)?;
    transactions_to_record_batch(&records)
}
