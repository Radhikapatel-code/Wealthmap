#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;

use crate::pipeline::EnginePipeline;
use crate::schema::{transactions_to_record_batch, TransactionRecord};

#[cfg(feature = "python")]
#[pyfunction]
pub fn compute_fifo_tax_json(txs_json: &str) -> PyResult<String> {
    let tx_records: Vec<TransactionRecord> = serde_json::from_str(txs_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid transaction JSON: {}", e)))?;

    let batch = transactions_to_record_batch(&tx_records)
        .map_err(|e| PyValueError::new_err(format!("Failed to build Arrow RecordBatch: {}", e)))?;

    let pipeline = EnginePipeline::new(vec![]);
    let (matched, agg) = pipeline
        .run(batch)
        .map_err(|e| PyValueError::new_err(format!("Engine pipeline execution error: {}", e)))?;

    let output = serde_json::json!({
        "matched_lots": matched,
        "aggregates": agg,
    });

    serde_json::to_string(&output)
        .map_err(|e| PyValueError::new_err(format!("Failed to serialize result: {}", e)))
}

#[cfg(feature = "python")]
#[pymodule]
fn wealthmap_engine(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_fifo_tax_json, m)?)?;
    Ok(())
}
